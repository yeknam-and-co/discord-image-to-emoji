from PIL import Image
import os
import math
import discord
import io
import string
import random
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True 

bot = discord.Bot()

@bot.event
async def on_ready():
    print(f'LOOOOOGINGED INNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN as {bot.user}')

@bot.slash_command(description="nuke emojis")
async def nukeemojis(ctx):
    deleted = 0
    failed = 0
    
    emojis_to_delete = list(ctx.guild.emojis)
    
    for emoji in emojis_to_delete:
        try:
            await emoji.delete()
            deleted += 1
        except Exception:
            failed += 1
    
    await ctx.respond(f"deleted {deleted} emojis. failed to delete {failed} emojis.")


def generate_short_name(length=2):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

@bot.slash_command(description="convert image into emojis")
async def imagetoemojis(ctx, image: discord.Attachment, size: int = 128, bio_mode: bool = False):
    await ctx.defer()
    
    if size < 16 or size > 128:
        await ctx.respond("size must be between 16 and 128 pixels")
        return
    
    temp_dir = "temp_emojis"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    image_data = await image.read()
    image_bytes = io.BytesIO(image_data) # sum binary shit

    # max emojis for bio mode
    max_bio_emojis = 9 if bio_mode else 100  
    
    total_pieces, grid_size = split_image_for_emojis(image_bytes, temp_dir, max_size=size, max_emojis=max_bio_emojis)

    emoji_names = []
    emoji_refs = []
    emoji_short_refs = []
    
    rows, cols = grid_size
    emoji_grid_array = [["" for i in range(cols)] for j in range(rows)]
    emoji_short_grid = [["" for i in range(cols)] for j in range(rows)]
    # 2d grid like that one chess board and also the lc i forgot
    
    used_names = set()

    for filename in os.listdir(temp_dir):
        if filename.endswith(".png") and filename != "preview.png":
            filepath = os.path.join(temp_dir, filename)

            base_name = os.path.splitext(filename)[0]
            parts = base_name.split('_')
            
            # OPTIMIZATION
            if bio_mode:
                while True:
                    emoji_name = generate_short_name(2)  
                    if emoji_name not in used_names:
                        used_names.add(emoji_name)
                        break
            else:
                if len(parts) >= 3:
                    try:
                        row_idx = int(parts[1])
                        col_idx = int(parts[2])
                        emoji_name = f"e{row_idx}{col_idx}" # the g5 in chess
                    except ValueError:
                        emoji_name = base_name.replace("emoji_", "e")
                else:
                    emoji_name = base_name.replace("emoji_", "e")

            with open(filepath, "rb") as img:
                try:
                    emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=img.read())
                    emoji_names.append(emoji_name)
                    
                    # what we use to display the emoji
                    emoji_ref = f"<:{emoji.name}:{emoji.id}>"
                    emoji_refs.append(emoji_ref)
                    
                    short_ref = f"{emoji.id}"
                    emoji_short_refs.append(short_ref)
                    
                    if len(parts) >= 3:
                        try:
                            row_idx = int(parts[1])
                            col_idx = int(parts[2])
                            if 0 <= row_idx < rows and 0 <= col_idx < cols:
                                emoji_grid_array[row_idx][col_idx] = emoji_ref
                                emoji_short_grid[row_idx][col_idx] = short_ref
                        except (ValueError, IndexError):
                            pass
                            
                except discord.HTTPException as e:
                    # rate limiting is gonna kill me
                    await ctx.respond(f"Error creating emoji {emoji_name}: {str(e)}")
                    return

    grid_text = ""
    for row in emoji_grid_array:
        row_text = "".join(ref for ref in row if ref)
        grid_text += row_text
        grid_text += "\n"
    
    grid_text = grid_text.rstrip()

    bio_text = ""
    for row in emoji_short_grid:
        bio_text += ",".join(ref for ref in row if ref)
        if any(row): 
            bio_text += ","
    
    if bio_text.endswith(","):
        bio_text = bio_text[:-1]
    
    bio_length = len(bio_text)
    bio_status = "fits in bio!" if bio_length <= 190 else f"too long for bio ({bio_length}/190)"

    embed = discord.Embed(
        title="image has been split!",
        description=f"total pieces: {total_pieces}, grid size: {rows}x{cols}"
    )
    
    embed.add_field(name="bio fommat", value=f"length: {bio_length}/190 chars\nstatus: {bio_status}", inline=False)
    embed.add_field(name="instructions", value="copy the emojis to your bio with this format:\n<:emoji1:ID1><:emoji2:ID2>...", inline=False)

    preview_path = os.path.join(temp_dir, 'preview.png')
    if os.path.exists(preview_path):
        file = discord.File(preview_path, filename="preview.png")
        embed.set_image(url="attachment://preview.png")
        await ctx.respond(embed=embed, file=file)
    else:
        await ctx.respond(embed=embed)

    await ctx.send("**showcase:**")
    await ctx.send(grid_text)
    
    if len("".join(emoji_refs)) < 1900:
        continuous_grid = ""
        for i in range(rows):
            for j in range(cols):
                if emoji_grid_array[i][j]:
                    continuous_grid += emoji_grid_array[i][j]
        if continuous_grid:
            await ctx.send("continuous version (no line breaks):")
            await ctx.send(continuous_grid)

    for filename in os.listdir(temp_dir):
        try:
            os.remove(os.path.join(temp_dir, filename))
        except:
            pass
    try:
        os.rmdir(temp_dir)
    except:
        pass

def split_image_for_emojis(image_source, output_dir, max_size=128, max_emojis=100):
    # does both file paths and BytesIO objects
    if isinstance(image_source, Image.Image):
        img = image_source
    else:
        img = Image.open(image_source)
    
    # convert to RGBA to ensure transparency support
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    original_width, original_height = img.size
    
    # calculate the optimal number of splits from getting the width and height of the image and dividing by the max size like 1920 / 128 = 15 and 1080 / 128 = 8
    cols = math.ceil(original_width / max_size)
    rows = math.ceil(original_height / max_size)
    
    # limit grid size based on max_emojis
    total_cells = rows * cols
    if total_cells > max_emojis:
        scale_factor = math.sqrt(max_emojis / total_cells)
        cols = min(cols, math.floor(cols * scale_factor))
        rows = min(rows, math.floor(rows * scale_factor))
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    pieces = []

    emoji_size = max_size
    
    # the grid's total size if all emojis were perfect 128x128 pieces
    grid_width = cols * emoji_size
    grid_height = rows * emoji_size
    
    transparent_canvas = Image.new('RGBA', (grid_width, grid_height), (0, 0, 0, 0))
    
    scale = min(grid_width / original_width, grid_height / original_height)
    new_width = int(original_width * scale)
    new_height = int(original_height * scale)
    
    if scale != 1:
        img = img.resize((new_width, new_height), Image.LANCZOS)
    
    paste_x = (grid_width - new_width) // 2
    paste_y = (grid_height - new_height) // 2
    
    transparent_canvas.paste(img, (paste_x, paste_y), img if img.mode == 'RGBA' else None)

    for row in range(rows):
        for col in range(cols):
            # calculate coordinates for cropping from the centered canvas
            left = col * emoji_size
            top = row * emoji_size
            right = left + emoji_size
            bottom = top + emoji_size
            
            # crop each piece to have like the perfect 128x128 size
            grid_piece = transparent_canvas.crop((left, top, right, bottom))
            
            has_content = False
            for x in range(0, emoji_size, 4):  
                for y in range(0, emoji_size, 4): # check every 4 pixels for speed and OPTIMIZATION and so my computer doesnt explode
                    if x < grid_piece.width and y < grid_piece.height:
                        pixel = grid_piece.getpixel((x, y))
                        if len(pixel) == 4 and pixel[3] > 0: # check if the pixel is transparent
                            has_content = True
                            break
                if has_content:
                    break
            
            if has_content:
                piece_filename = f'emoji_{row}_{col}.png'
                output_path = os.path.join(output_dir, piece_filename)
                grid_piece.save(output_path, optimize=True, quality=90)
                pieces.append((row, col, grid_piece))
    
    # create the preview image
    preview_width = min(grid_width, 1024)  
    preview_height = min(grid_height, 1024)
    scale_factor = min(preview_width / grid_width, preview_height / grid_height)
    
    if scale_factor < 1:
        preview_width = int(grid_width * scale_factor)
        preview_height = int(grid_height * scale_factor)
    
    preview_image = Image.new('RGBA', (preview_width, preview_height), (0, 0, 0, 0))
    
    if scale_factor < 1:
        scaled_preview = transparent_canvas.resize((preview_width, preview_height), Image.LANCZOS)
        preview_image.paste(scaled_preview, (0, 0), scaled_preview)
    else:
        preview_image.paste(transparent_canvas, (0, 0), transparent_canvas)
    
    # add lines to show what we did
    draw = Image.new('RGBA', preview_image.size, (0, 0, 0, 0))
    
    for i in range(1, rows):
        y = int(i * emoji_size * scale_factor)
        for x in range(preview_width):
            if 0 <= y < preview_height:
                draw.putpixel((x, y), (100, 100, 100, 128))  
    
    for i in range(1, cols):
        x = int(i * emoji_size * scale_factor)
        for y in range(preview_height):
            if 0 <= x < preview_width:
                draw.putpixel((x, y), (100, 100, 100, 128))  
    
    preview_image = Image.alpha_composite(preview_image, draw)

    preview_image.save(os.path.join(output_dir, 'preview.png'), optimize=True)
    
    return len(pieces), (rows, cols)

if __name__ == "__main__":
    if not token:
        print("discord token not found in .env file")
        print("please create a .env file with your token: DISCORD_TOKEN=your_token_here")
        exit(1)
    bot.run(token)