# @copyright 2025 Peyronon Arno
import os
import json
import aiohttp
import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button
from urllib.parse import urlparse, parse_qs
import async_timeout
import random

CONFIG_FILE = "config.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
]


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print(f"\u274c Erreur lecture {CONFIG_FILE}")
        return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


config_json = load_config()

channel_configs = {}

for channel_id, filters in config_json.items():
    if isinstance(filters, dict):
        channel_configs[channel_id] = filters

token = os.environ.get("TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

cache_urls_per_channel = {channel_id: set() for channel_id in channel_configs}
tasks = {}


async def get_vinted_items_async(filters):
    url = "https://www.vinted.fr/api/v2/catalog/items"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.vinted.fr/vetements",
    }

    base_params = {
        "search_text": filters.get("search_text", ""),
        "price_from": filters.get("price_min", 0),
        "price_to": filters.get("price_max", 9999),
        "currency": filters.get("currency", "EUR"),
        "page": 1,
        "per_page": 5,
        "order": "newest_first",
    }

    for key in ["catalog_ids", "brand_ids", "status_ids", "color_ids", "size_ids"]:
        if filters.get(key):
            base_params[key] = ",".join(map(str, filters[key]))

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with async_timeout.timeout(10):
                async with session.get(url, params=base_params) as resp:
                    if resp.status != 200:
                        print(f"\u274c API Vinted retourne {resp.status}")
                        return []
                    data = await resp.json()
                    return data.get("items", [])
    except asyncio.TimeoutError:
        print("\u23f1\ufe0f Timeout Vinted API")
        return []
    except Exception as e:
        print(f"\u274c Erreur r\u00e9seau Vinted : {e}")
        return []


async def check_channel_loop(channel_id, filters, interval=5):
    print(f"\U0001f7e2 D\u00e9marrage boucle check pour channel {channel_id}")
    while True:
        print(f"\U0001f501 Check items pour channel {channel_id}")
        try:
            items = await get_vinted_items_async(filters)
            print(f"Nombre d'items r\u00e9cup\u00e9r\u00e9s : {len(items)}")
        except Exception as e:
            print(f"\u274c Erreur fetch items : {e}")
            items = []

        if items:
            channel = bot.get_channel(int(channel_id))
            if channel is None:
                print(f"\u26a0\ufe0f Channel {channel_id} introuvable")
            else:
                for i, item in enumerate(items):
                    if i >= 3:
                        break

                    url = item.get("url")
                    if url in cache_urls_per_channel[channel_id]:
                        continue

                    cache_urls_per_channel[channel_id].add(url)

                    brand = item.get("brand_title", "N/A")
                    size = item.get("size_title") or "Non pr\u00e9cis\u00e9e"
                    status = item.get("status", "N/A")
                    price = (
                        f"{item['price']['amount']} {item['price']['currency_code']}"
                    )
                    title = item.get("title", "Annonce Vinted")

                    user = item.get("user", {})
                    seller_name = user.get("login", "Vendeur inconnu")
                    is_business = (
                        "\U0001f454 Pro"
                        if user.get("business", False)
                        else "\U0001f9d1 Particulier"
                    )

                    photo = item.get("photo", {})
                    thumbnails = photo.get("thumbnails", [])
                    main_image = photo.get("url")
                    image_urls = [main_image] if main_image else []

                    seen_urls = set(image_urls)
                    for thumb in thumbnails:
                        thumb_url = thumb.get("url")
                        if thumb_url and thumb_url not in seen_urls:
                            image_urls.append(thumb_url)
                            seen_urls.add(thumb_url)
                        if len(image_urls) >= 3:
                            break

                    embed = discord.Embed(
                        title=title,
                        url=url,
                        description=(
                            f"\U0001f464 **{seller_name}**\n"
                            f"{is_business}\n"
                            f"\U0001f45f {brand} | \U0001f4cf Taille : {size}"
                        ),
                        color=0x00B2FF,
                    )
                    embed.add_field(
                        name="\U0001f6cd\ufe0f \u00c9tat", value=status, inline=True
                    )
                    embed.add_field(name="💸 Prix", value=price, inline=True)
                    if image_urls:
                        embed.set_image(url=image_urls[0])
                    embed.set_footer(text="Vinted Bot • Nouvelle annonce")

                    view = View()
                    button = Button(label="🛍️ Voir l'annonce", url=url)
                    view.add_item(button)

                    try:
                        await channel.send(embed=embed, view=view)
                    except Exception as e:
                        print(f"Erreur en envoyant dans {channel.name} : {e}")
        await asyncio.sleep(random.uniform(3, 7))


def parse_vinted_url_to_filters(url):
    try:
        print(f"🔍 Parsing URL : {url}")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        print(f"📦 Query parsed : {query}")

        def get_ids(key):
            return [
                int(v)
                for k, vs in query.items()
                if k.startswith(key)
                for v in vs
                if v.isdigit()
            ]

        filters = {
            "search_text": query.get("search_text", [""])[0],
            "price_min": int(query.get("price_from", [0])[0]),
            "price_max": int(query.get("price_to", [9999])[0]),
            "catalog_ids": get_ids("catalog"),
            "brand_ids": get_ids("brand_ids"),
            "status_ids": get_ids("status_ids"),
            "color_ids": get_ids("color_ids"),
            "size_ids": get_ids("size_ids"),
            "currency": query.get("currency", ["EUR"])[0],
        }

        return filters
    except Exception as e:
        print(f"Erreur parse_vinted_url_to_filters : {e}")
        return None


async def clear_channel_cache_loop():
    while True:
        print("🧹 Purge des caches URL par salon...")
        for channel_id in cache_urls_per_channel:
            print(
                f"   - Vider le cache du salon {channel_id} ({len(cache_urls_per_channel[channel_id])} éléments)"
            )
            cache_urls_per_channel[channel_id].clear()
        await asyncio.sleep(3600)


@bot.command()
async def add_vinted_channel(ctx, url: str, readonly: bool = False):
    channel_id = str(ctx.channel.id)

    existing_config = config_json.get(channel_id)
    if existing_config and existing_config.get("readonly", False):
        await ctx.send("🔒 Ce salon est en mode readonly. Configuration inchangée.")
        return

    filters = parse_vinted_url_to_filters(url)
    if not filters:
        await ctx.send("❌ URL invalide ou filtres non reconnus.")
        return

    filters["readonly"] = readonly

    channel_configs[channel_id] = filters
    cache_urls_per_channel[channel_id] = set()

    try:
        config_json[channel_id] = filters
        save_config(config_json)
    except Exception as e:
        await ctx.send(f"❌ Erreur sauvegarde config : {e}")
        return

    if channel_id in tasks:
        tasks[channel_id].cancel()
    tasks[channel_id] = asyncio.create_task(
        check_channel_loop(channel_id, filters, interval=5)
    )

    await ctx.send(
        f"✅ Configuration {'readonly' if readonly else 'modifiable'} "
        f"ajoutée et monitoring lancé pour ce salon."
    )


@bot.command()
@commands.has_permissions(manage_channels=True)
async def add_channel(ctx, name: str, url: str, readonly: bool = False):
    """Crée un salon texte + configure le monitoring Vinted dessus"""
    guild = ctx.guild
    existing_channel = discord.utils.get(guild.channels, name=name)

    if existing_channel:
        await ctx.send(f"⚠️ Un salon nommé `{name}` existe déjà.")
        return

    try:
        new_channel = await guild.create_text_channel(name)
        await ctx.send(f"✅ Salon créé : {new_channel.mention}")
    except Exception as e:
        await ctx.send(f"❌ Erreur création salon : {e}")
        return

    if url:
        filters = parse_vinted_url_to_filters(url)
        if not filters:
            await ctx.send("❌ URL invalide ou filtres non reconnus.")
            return

        filters["readonly"] = readonly
        channel_id = str(new_channel.id)

        channel_configs[channel_id] = filters
        cache_urls_per_channel[channel_id] = set()

        try:
            config_json[channel_id] = filters
            save_config(config_json)
        except Exception as e:
            await ctx.send(f"❌ Erreur sauvegarde config : {e}")
            return

        tasks[channel_id] = asyncio.create_task(
            check_channel_loop(channel_id, filters, interval=5)
        )

        await ctx.send(
            f"🛠️ Salon `{name}` configuré avec succès ! "
            f"Mode : {'readonly' if readonly else 'modifiable'}"
        )


@bot.command()
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx):
    channel = ctx.channel
    channel_id = str(channel.id)

    task = tasks.pop(channel_id, None)
    if task:
        task.cancel()

    channel_configs.pop(channel_id, None)
    cache_urls_per_channel.pop(channel_id, None)
    if channel_id in config_json:
        config_json.pop(channel_id)
        save_config(config_json)

    try:
        await ctx.send("🗑️ Salon en cours de suppression...")
        await channel.delete()
    except Exception as e:
        await ctx.send(f"❌ Erreur suppression salon : {e}")


@bot.command()
async def show_config(ctx):
    channel_id = str(ctx.channel.id)
    filters = channel_configs.get(channel_id)
    if not filters:
        await ctx.send("❌ Ce salon n'a pas de configuration.")
        return
    msg = (
        f"Filtres pour ce salon :\n"
        f"- search_text : {filters.get('search_text', '')}\n"
        f"- brands : {filters.get('brands', [])}\n"
        f"- status_ids : {filters.get('status_ids', [])}\n"
        f"- price_min : {filters.get('price_min', 0)}\n"
        f"- price_max : {filters.get('price_max', 9999)}\n"
        f"- readonly : {filters.get('readonly', False)}"
    )
    await ctx.send(msg)


@bot.command()
async def stop(ctx):
    channel_id = str(ctx.channel.id)

    if channel_id not in channel_configs:
        await ctx.send("❌ Ce salon n'a pas de configuration active.")
        return

    channel_configs.pop(channel_id, None)
    cache_urls_per_channel.pop(channel_id, None)

    task = tasks.pop(channel_id, None)
    if task:
        task.cancel()

    if channel_id in config_json:
        config_json.pop(channel_id)
        save_config(config_json)

    await ctx.send("🛑 Monitoring arrêté et configuration supprimée pour ce salon.")


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user.name}")
    print(channel_configs)
    for channel_id, filters in channel_configs.items():
        tasks[channel_id] = asyncio.create_task(
            check_channel_loop(channel_id, filters, interval=5)
        )
    asyncio.create_task(clear_channel_cache_loop())


@bot.event
async def on_disconnect():
    print("🔌 Le bot a été déconnecté de Discord.")


@bot.event
async def on_resumed():
    print("🔄 Le bot a repris une session Discord après une déconnexion.")


bot.run(token)
# @copyright 2025 Peyronon Arno
