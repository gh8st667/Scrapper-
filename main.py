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
import hashlib
import uuid

CONFIG_FILE = "config.json"

# User-Agents encore plus récents et variés
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
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

# Session globale avec réinitialisation périodique
global_session = None
session_created_at = 0
last_request_time = {}


async def create_stealth_session():
    """Crée une session avec maximum de stealth"""

    # Générer un fingerprint unique
    session_id = str(uuid.uuid4())[:8]
    timestamp = str(int(time.time() * 1000))

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.vinted.fr/",
        "Origin": "https://www.vinted.fr",
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "X-Requested-With": "XMLHttpRequest",
        "X-Session-Id": session_id,
        "X-Timestamp": timestamp,
    }

    # Configuration avancée du connector
    connector = aiohttp.TCPConnector(
        limit=5,  # Limite encore plus les connexions
        limit_per_host=2,
        ttl_dns_cache=300,
        use_dns_cache=True,
        enable_cleanup_closed=True,
        force_close=True,  # Force la fermeture des connexions
        ssl=False,  # Désactive SSL pour éviter les checks
    )

    timeout = aiohttp.ClientTimeout(total=20, connect=15, sock_read=10)

    session = aiohttp.ClientSession(
        headers=headers,
        connector=connector,
        timeout=timeout,
        cookie_jar=aiohttp.CookieJar(),
        trust_env=True,
    )

    return session


async def get_session():
    """Récupère la session globale et la recrée si nécessaire"""
    global global_session, session_created_at

    current_time = time.time()

    # Recrée la session toutes les 10 minutes
    if (
        global_session is None
        or global_session.closed
        or current_time - session_created_at > 300
    ):

        if global_session and not global_session.closed:
            await global_session.close()

        print("🔄 Création d'une nouvelle session stealth")
        global_session = await create_stealth_session()
        session_created_at = current_time

        # Warmup de la session avec plusieurs pages
        await warmup_session(global_session)

    return global_session


async def warmup_session(session):
    """Chauffe la session en visitant plusieurs pages comme un humain"""
    warmup_urls = [
        "https://www.vinted.fr/",
        "https://www.vinted.fr/vetements",
        "https://www.vinted.fr/femmes/vetements",
    ]

    for url in warmup_urls:
        try:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    await resp.text()
            await asyncio.sleep(random.uniform(1, 3))
        except:
            pass  # Ignore les erreurs de warmup


def generate_request_signature():
    """Génère une signature unique pour chaque requête"""
    timestamp = str(int(time.time() * 1000))
    random_str = str(uuid.uuid4())[:8]
    signature = hashlib.md5(f"{timestamp}{random_str}".encode()).hexdigest()[:16]
    return timestamp, signature


async def get_vinted_items_async(filters, channel_id):
    """Version ultra-stealth avec techniques d'évasion avancées"""
    current_time = time.time()

    # Rate limiting STRICT : minimum 15 secondes entre requêtes par channel
    if channel_id in last_request_time:
        time_since_last = current_time - last_request_time[channel_id]
        min_delay = 15 + random.uniform(0, 5)  # 15-20 secondes
        if time_since_last < min_delay:
            await asyncio.sleep(min_delay - time_since_last)

    last_request_time[channel_id] = time.time()

    # Paramètres de base avec anti-détection
    timestamp, signature = generate_request_signature()

    base_params = {
        "search_text": filters.get("search_text", ""),
        "price_from": filters.get("price_min", 0),
        "price_to": filters.get("price_max", 9999),
        "currency": filters.get("currency", "EUR"),
        "page": 1,
        "per_page": 6,  # Encore moins d'items
        "order": "newest_first",
        "_": timestamp,
        "sig": signature,
        "v": "2.1",
        "locale": "fr",
        "t": int(time.time()),
    }

    for key in ["catalog_ids", "brand_ids", "status_ids", "color_ids", "size_ids"]:
        if filters.get(key):
            base_params[key] = ",".join(map(str, filters[key]))

    max_retries = 2  # Moins de retry pour éviter d'insister
    for attempt in range(max_retries):
        try:
            session = await get_session()

            # Simuler navigation humaine AVANT chaque requête API
            if random.random() < 0.3:  # 30% de chance
                try:
                    browse_url = random.choice(
                        [
                            "https://www.vinted.fr/vetements",
                            "https://www.vinted.fr/femmes",
                            "https://www.vinted.fr/hommes",
                        ]
                    )
                    async with session.get(browse_url) as browse_resp:
                        if browse_resp.status == 200:
                            await browse_resp.text()
                    await asyncio.sleep(random.uniform(2, 4))
                except:
                    pass

            # Headers spécifiques pour cette requête
            request_headers = {
                "X-Request-ID": str(uuid.uuid4()),
                "X-Client-Version": "web-2.1.0",
                "X-Timestamp": timestamp,
                "X-Signature": signature,
            }

            async with async_timeout.timeout(15):
                async with session.get(
                    "https://www.vinted.fr/api/v2/catalog/items",
                    params=base_params,
                    headers=request_headers,
                    allow_redirects=True,
                ) as resp:

                    response_text = await resp.text()

                    if resp.status == 200:
                        try:
                            data = json.loads(response_text)
                            items = data.get("items", [])
                            print(
                                f"✅ {len(items)} items récupérés pour channel {channel_id}"
                            )
                            return items
                        except json.JSONDecodeError:
                            print(f"❌ Réponse invalide pour channel {channel_id}")
                            return []

                    elif resp.status == 403:
                        print(
                            f"🚫 403 - IP probablement blacklistée pour channel {channel_id}"
                        )
                        # En cas de 403, attendre BEAUCOUP plus longtemps
                        if attempt < max_retries - 1:
                            delay = 60 + random.uniform(0, 30)  # 1-1.5 minutes
                            print(f"⏸️ Pause de {delay:.1f}s avant retry")
                            await asyncio.sleep(delay)
                            # Forcer la recréation de session
                            global global_session, session_created_at
                            if global_session and not global_session.closed:
                                await global_session.close()
                            global_session = None
                            session_created_at = 0
                            continue

                    elif resp.status == 429:
                        print(f"⚠️ Rate limit sévère détecté pour channel {channel_id}")
                        await asyncio.sleep(random.uniform(30, 60))  # 30s-1min
                        continue

                    elif resp.status in [500, 502, 503]:
                        print(
                            f"⚠️ Erreur serveur {resp.status} pour channel {channel_id}"
                        )
                        await asyncio.sleep(random.uniform(10, 20))
                        continue

                    else:
                        print(
                            f"❌ Erreur API Vinted pour channel {channel_id}: {resp.status}"
                        )
                        print(f"Response: {response_text[:200]}...")
                        return []

        except asyncio.TimeoutError:
            print(
                f"⏱️ Timeout pour channel {channel_id}, tentative {attempt + 1}/{max_retries}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(10, 20))
        except Exception as e:
            print(f"❌ Exception get_vinted_items_async channel {channel_id}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(5, 15))

    return []


async def check_channel_loop(channel_id, filters, interval=25):
    """Boucle avec interval BEAUCOUP plus élevé"""
    print(
        f"🟢 Démarrage boucle check pour channel {channel_id} (interval: {interval}s)"
    )
    consecutive_errors = 0
    last_success = time.time()

    while True:
        print(f"🔄 Check items pour channel {channel_id}")

        try:
            items = await get_vinted_items_async(filters, channel_id)

            if not items:
                consecutive_errors += 1
                print(
                    f"Aucun item trouvé pour channel {channel_id} (erreurs consécutives: {consecutive_errors})"
                )

                # Si trop d'erreurs, pause très longue
                if consecutive_errors > 3:
                    pause_time = min(consecutive_errors * 30, 300)  # Max 5 minutes
                    print(f"🛑 Pause de {pause_time}s pour channel {channel_id}")
                    await asyncio.sleep(pause_time)
                    continue

            else:
                consecutive_errors = 0
                last_success = time.time()

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
                            await asyncio.sleep(1)  # Délai entre envois Discord
                        except Exception as e:
                            print(f"Erreur en envoyant dans {channel.name} : {e}")

        except Exception as e:
            consecutive_errors += 1
            print(f"❌ Erreur générale channel {channel_id}: {e}")

        # Si pas de succès depuis > 30 minutes, pause très longue
        if time.time() - last_success > 1800:  # 30 minutes
            print(
                f"😴 Aucun succès depuis 30min pour channel {channel_id}, pause de 10min"
            )
            await asyncio.sleep(600)  # 10 minutes
            last_success = time.time()  # Reset

        # Interval très élevé avec randomisation
        current_interval = interval + random.uniform(5, 15)
        await asyncio.sleep(current_interval)


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
            if cache_size > 50:  # Cache encore plus petit
                urls_list = list(cache_urls_per_channel[channel_id])
                cache_urls_per_channel[channel_id] = set(urls_list[-25:])
                print(
                    f"   - Cache du salon {channel_id} réduit de {cache_size} à 25 éléments"
                )
        await asyncio.sleep(1800)


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

    # Interval très élevé : 25 secondes minimum
    tasks[channel_id] = asyncio.create_task(
        check_channel_loop(channel_id, filters, interval=25)
    )

    await ctx.send(
        f"✅ Configuration {'readonly' if readonly else 'modifiable'} "
        f"ajoutée et monitoring lancé pour ce salon (interval: 25s minimum).\n"
        f"⚠️ **Nouveau système ultra-stealth activé** - Les requêtes seront BEAUCOUP plus espacées pour éviter les blocages."
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
            check_channel_loop(channel_id, filters, interval=25)
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
    print(f"📋 Configurations chargées: {len(channel_configs)}")

    for channel_id, filters in channel_configs.items():
        # Délai important entre chaque démarrage pour éviter le spam
        await asyncio.sleep(random.uniform(5, 15))
        tasks[channel_id] = asyncio.create_task(
            check_channel_loop(channel_id, filters, interval=25)
        )

    asyncio.create_task(clear_channel_cache_loop())
    print("🚀 Toutes les tâches lancées avec système ultra-stealth")


@bot.event
async def on_disconnect():
    print("🔌 Le bot a été déconnecté de Discord.")


@bot.event
async def on_resumed():
    print("🔄 Le bot a repris une session Discord après une déconnexion.")


# Nettoyage à la fermeture
async def cleanup():
    global global_session
    if global_session and not global_session.closed:
        await global_session.close()


import atexit

atexit.register(lambda: asyncio.run(cleanup()))

bot.run(token)
# @copyright 2025 Peyronon Arno
