# @copyright 2025 Peyronon Arno
import os
import json
import aiohttp
import async_timeout
import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
from urllib.parse import urlparse, parse_qs
import random
import time
from aiohttp_socks import ProxyConnector

CONFIG_FILE = "config.json"

# Pool de User-Agents réalistes
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]

# Pool de referers réalistes
REFERERS = [
    "https://www.vinted.fr/",
    "https://www.vinted.fr/vetements",
    "https://www.vinted.fr/femmes",
    "https://www.vinted.fr/hommes",
    "https://www.google.com/",
    "https://www.google.fr/",
]


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print(f"❌ Erreur lecture {CONFIG_FILE}")
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

# Session partagée avec rotation des headers
session_pool = []
current_session_index = 0
last_request_time = {}


async def get_session():
    """Récupère une session avec des headers rotatifs"""
    global current_session_index

    if not session_pool:
        await create_session_pool()

    session = session_pool[current_session_index]
    current_session_index = (current_session_index + 1) % len(session_pool)
    return session


async def create_session_pool():
    """Crée un pool de sessions avec différents headers"""
    global session_pool

    for _ in range(3):  # 3 sessions différentes
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": random.choice(REFERERS),
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        # Configuration du connector avec timeout plus long
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )

        timeout = aiohttp.ClientTimeout(total=15, connect=10)
        session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout,
            cookie_jar=aiohttp.CookieJar(),
        )
        session_pool.append(session)


async def simulate_human_behavior():
    """Simule un comportement humain avec des délais aléatoires"""
    await asyncio.sleep(random.uniform(0.5, 2.0))


async def get_vinted_items_async(filters, channel_id):
    """Version améliorée avec gestion des erreurs et retry"""
    current_time = time.time()

    # Rate limiting par channel (minimum 3 secondes entre les requêtes)
    if channel_id in last_request_time:
        time_since_last = current_time - last_request_time[channel_id]
        if time_since_last < 3:
            await asyncio.sleep(3 - time_since_last)

    last_request_time[channel_id] = time.time()

    base_params = {
        "search_text": filters.get("search_text", ""),
        "price_from": filters.get("price_min", 0),
        "price_to": filters.get("price_max", 9999),
        "currency": filters.get("currency", "EUR"),
        "page": 1,
        "per_page": 8,  # Réduit pour éviter les timeouts
        "order": "newest_first",
    }

    for key in ["catalog_ids", "brand_ids", "status_ids", "color_ids", "size_ids"]:
        if filters.get(key):
            base_params[key] = ",".join(map(str, filters[key]))

    max_retries = 3
    for attempt in range(max_retries):
        try:
            session = await get_session()

            # Simuler une visite de la page principale d'abord
            if attempt == 0:  # Seulement au premier essai
                try:
                    async with session.get(
                        "https://www.vinted.fr", ssl=False
                    ) as warmup:
                        await warmup.text()
                    await simulate_human_behavior()
                except:
                    pass  # On ignore les erreurs de warmup

            # Requête principale avec timeout plus court
            async with async_timeout.timeout(12):
                # Ajouter des paramètres anti-détection
                extra_params = {
                    "timestamp": int(time.time() * 1000),
                    "_": int(time.time() * 1000) + random.randint(1, 1000),
                }
                final_params = {**base_params, **extra_params}

                async with session.get(
                    "https://www.vinted.fr/api/v2/catalog/items",
                    params=final_params,
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", [])
                        print(
                            f"✅ {len(items)} items récupérés pour channel {channel_id}"
                        )
                        return items
                    elif resp.status == 403:
                        print(
                            f"⚠️ 403 détecté pour channel {channel_id}, tentative {attempt + 1}/{max_retries}"
                        )
                        if attempt < max_retries - 1:
                            # Délai exponentiel + randomisation
                            delay = (2**attempt) + random.uniform(1, 3)
                            await asyncio.sleep(delay)
                            continue
                    elif resp.status == 429:
                        print(f"⚠️ Rate limit détecté pour channel {channel_id}")
                        await asyncio.sleep(random.uniform(5, 10))
                        continue
                    else:
                        print(
                            f"❌ Erreur API Vinted pour channel {channel_id}: {resp.status}"
                        )
                        return []

        except asyncio.TimeoutError:
            print(
                f"⏱️ Timeout pour channel {channel_id}, tentative {attempt + 1}/{max_retries}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(2, 5))
        except Exception as e:
            print(
                f"❌ Exception get_vinted_items_async channel {channel_id}, tentative {attempt + 1}: {e}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(1, 3))

    return []


async def check_channel_loop(channel_id, filters, interval=8):
    """Boucle de vérification avec interval adaptatif"""
    print(f"🟢 Démarrage boucle check pour channel {channel_id}")
    consecutive_errors = 0

    while True:
        print(f"🔄 Check items pour channel {channel_id}")

        try:
            items = await get_vinted_items_async(filters, channel_id)

            if not items:
                consecutive_errors += 1
                print(
                    f"Aucun item trouvé pour channel {channel_id} (erreurs consécutives: {consecutive_errors})"
                )
            else:
                consecutive_errors = 0  # Reset du compteur d'erreurs
                channel = bot.get_channel(int(channel_id))
                if channel is None:
                    print(f"⚠️ Channel {channel_id} introuvable")
                else:
                    for item in items:
                        url = item.get("url")
                        if url in cache_urls_per_channel[channel_id]:
                            continue

                        cache_urls_per_channel[channel_id].add(url)

                        brand = item.get("brand_title", "N/A")
                        size = item.get("size_title") or "Non précisée"
                        status = item.get("status", "N/A")
                        price = f"{item['price']['amount']} {item['price']['currency_code']}"
                        title = item.get("title", "Annonce Vinted")

                        user = item.get("user", {})
                        seller_name = user.get("login", "Vendeur inconnu")
                        is_business = (
                            "👔 Pro"
                            if user.get("business", False)
                            else "🧑 Particulier"
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
                                f"👤 **{seller_name}**\n"
                                f"{is_business}\n"
                                f"👟 {brand} | 📏 Taille : {size}"
                            ),
                            color=0x00B2FF,
                        )
                        embed.add_field(name="🛍️ État", value=status, inline=True)
                        embed.add_field(name="💸 Prix", value=price, inline=True)
                        if image_urls:
                            embed.set_image(url=image_urls[0])
                        embed.set_footer(text="Vinted Bot • Nouvelle annonce")

                        view = View()
                        button = Button(label="🛍️ Voir l'annonce", url=url)
                        view.add_item(button)

                        try:
                            await channel.send(embed=embed, view=view)
                            # Petit délai entre les envois Discord
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"Erreur en envoyant dans {channel.name} : {e}")

        except Exception as e:
            consecutive_errors += 1
            print(f"❌ Erreur générale channel {channel_id}: {e}")

        # Interval adaptatif basé sur les erreurs
        if consecutive_errors > 5:
            current_interval = min(interval * 2, 30)  # Max 30 secondes
            print(
                f"⚠️ Nombreuses erreurs pour channel {channel_id}, interval augmenté à {current_interval}s"
            )
        elif consecutive_errors > 2:
            current_interval = interval + 5
        else:
            current_interval = interval

        await asyncio.sleep(current_interval + random.uniform(-1, 1))


def parse_vinted_url_to_filters(url):
    try:
        print(f"🔍 Parsing URL : {url}")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        print(f"📦 Query parsed : {query}")

        def get_ids(*possible_keys):
            ids = []
            for key in possible_keys:
                for k, vs in query.items():
                    if k.startswith(key):
                        for v in vs:
                            try:
                                ids.append(int(v))
                            except ValueError:
                                pass
            return ids

        filters = {
            "search_text": query.get("search_text", [""])[0],
            "price_min": (
                int(query.get("price_from", [0])[0])
                if query.get("price_from", [None])[0]
                else 0
            ),
            "price_max": (
                int(query.get("price_to", [9999])[0])
                if query.get("price_to", [None])[0]
                else 9999
            ),
            "catalog_ids": get_ids("catalog", "catalog_ids", "catalog_ids[]"),
            "brand_ids": get_ids("brand_ids", "brand_ids[]"),
            "status_ids": get_ids("status_ids", "status_ids[]"),
            "color_ids": get_ids("color_ids", "color_ids[]"),
            "size_ids": get_ids("size_ids", "size_ids[]"),
            "currency": query.get("currency", ["EUR"])[0],
        }

        return filters
    except Exception as e:
        print(f"❌ Erreur parse_vinted_url_to_filters : {e}")
        return None


async def clear_channel_cache_loop():
    while True:
        print("🧹 Purge des caches URL par salon...")
        for channel_id in cache_urls_per_channel:
            cache_size = len(cache_urls_per_channel[channel_id])
            if cache_size > 100:  # Limite le cache à 100 URLs par channel
                # Garde seulement les 50 plus récentes
                urls_list = list(cache_urls_per_channel[channel_id])
                cache_urls_per_channel[channel_id] = set(urls_list[-50:])
                print(
                    f"   - Cache du salon {channel_id} réduit de {cache_size} à 50 éléments"
                )
            else:
                print(f"   - Cache du salon {channel_id}: {cache_size} éléments")
        await asyncio.sleep(1800)  # Toutes les 30 minutes au lieu d'1h


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

    # Interval plus élevé pour éviter les blocages
    tasks[channel_id] = asyncio.create_task(
        check_channel_loop(channel_id, filters, interval=8)
    )

    await ctx.send(
        f"✅ Configuration {'readonly' if readonly else 'modifiable'} "
        f"ajoutée et monitoring lancé pour ce salon (interval: 8s)."
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
            check_channel_loop(channel_id, filters, interval=8)
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

    # Initialiser le pool de sessions
    await create_session_pool()

    print(f"📋 Configurations chargées: {len(channel_configs)}")
    for channel_id, filters in channel_configs.items():
        # Délai progressif pour éviter le spam au démarrage
        await asyncio.sleep(random.uniform(1, 3))
        tasks[channel_id] = asyncio.create_task(
            check_channel_loop(channel_id, filters, interval=8)
        )

    asyncio.create_task(clear_channel_cache_loop())
    print("🚀 Toutes les tâches lancées")


@bot.event
async def on_disconnect():
    print("🔌 Le bot a été déconnecté de Discord.")


@bot.event
async def on_resumed():
    print("🔄 Le bot a repris une session Discord après une déconnexion.")


async def cleanup_sessions():
    """Nettoie les sessions à la fermeture"""
    for session in session_pool:
        if not session.closed:
            await session.close()


# Ajout du nettoyage des sessions à la fermeture
import atexit

atexit.register(lambda: asyncio.run(cleanup_sessions()))

bot.run(token)
# @copyright 2025 Peyronon Arno
