import logging
import asyncio
import re
import urllib.parse
import sqlite3
from typing import List, Dict, Optional
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import Forbidden, TimedOut
from bs4 import BeautifulSoup
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import hypercorn.asyncio
from hypercorn.config import Config
import base64
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Настройки из переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7846698102:AAFR2bhmjAkPiV-PjtnFIu_oRnzxYPP1xVo')
ADMIN_ID = os.getenv('ADMIN_ID', '854773231')
UPLOAD_FOLDER = 'uploads'
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://apartment-bot-81rv.onrender.com/webhook')
KUFAR_LIMIT = int(os.getenv('KUFAR_LIMIT', 7))
PARSE_INTERVAL = int(os.getenv('PARSE_INTERVAL', 5))
USER_AGENT = os.getenv('USER_AGENT', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CITIES = {
    "minsk": "Минск",
    "brest": "Брест",
    "grodno": "Гродно",
    "gomel": "Гомель",
    "vitebsk": "Витебск",
    "mogilev": "Могилев",
}

def init_db():
    with sqlite3.connect("ads.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                link TEXT PRIMARY KEY,
                source TEXT,
                city TEXT,
                price INTEGER,
                rooms INTEGER,
                address TEXT,
                image TEXT,
                description TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS new_ads (
                link TEXT PRIMARY KEY,
                source TEXT,
                city TEXT,
                price INTEGER,
                rooms INTEGER,
                address TEXT,
                image TEXT,
                description TEXT,
                user_id TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                images TEXT,
                city TEXT,
                rooms INTEGER,
                price INTEGER,
                address TEXT,
                description TEXT,
                phone TEXT,
                timestamp TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()

init_db()

app = Flask(__name__, static_folder='static', static_url_path='')

class ApartmentParser:
    @staticmethod
    async def fetch_ads(city: str, min_price: Optional[int] = None, max_price: Optional[int] = None, rooms: Optional[int] = None) -> List[Dict]:
        headers = {"User-Agent": USER_AGENT}
        results = []
        url = f"https://re.kufar.by/l/{city}/snyat/kvartiru-dolgosrochno"
        if rooms:
            url += f"/{rooms}k"
        query_params = {"cur": "USD"}
        if min_price and max_price:
            query_params["prc"] = f"r:{min_price},{max_price}"
        url += f"?{urllib.parse.urlencode(query_params, safe=':,')}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    response.raise_for_status()
                    soup = BeautifulSoup(await response.text(), "html.parser")
                    for ad in soup.select("section > a"):
                        try:
                            link = ad.get("href", "").split('?')[0]
                            if not link:
                                continue
                                
                            price = ApartmentParser._parse_price(ad)
                            rooms_count = ApartmentParser._parse_rooms(ad)
                            address = ApartmentParser._parse_address(ad)
                            image = ApartmentParser._parse_image(ad)
                            description = ApartmentParser._parse_description(ad)
                            
                            if not price or not address:
                                continue
                                
                            results.append({
                                "link": link,
                                "source": "Kufar",
                                "city": city,
                                "price": price,
                                "rooms": rooms_count,
                                "address": address,
                                "image": image,
                                "description": description
                            })
                        except Exception as e:
                            logger.error(f"Ошибка парсинга объявления: {e}")
            except Exception as e:
                logger.error(f"Ошибка запроса: {e}")
        return results

    @staticmethod
    def _parse_price(ad) -> Optional[int]:
        price_element = ad.select_one(".styles_price__usd__HpXMa")
        return int(re.sub(r"[^\d]", "", price_element.text)) if price_element else None

    @staticmethod
    def _parse_rooms(ad) -> Optional[int]:
        rooms_element = ad.select_one(".styles_parameters__7zKlL")
        match = re.search(r"\d+", rooms_element.text) if rooms_element else None
        return int(match.group()) if match else None

    @staticmethod
    def _parse_address(ad) -> str:
        address_element = ad.select_one(".styles_address__l6Qe_")
        return address_element.text.strip() if address_element else "Не указано"

    @staticmethod
    def _parse_image(ad) -> Optional[str]:
        image_element = ad.select_one("img[src^='http']")
        return image_element.get("src") if image_element else None

    @staticmethod
    def _parse_description(ad) -> str:
        desc_element = ad.select_one(".styles_body__5BrnC")
        return desc_element.text.strip() if desc_element else "Без описания"

async def fetch_and_store_ads(user_filters: Dict = None):
    try:
        user_id = user_filters.get('user_id', 'default') if user_filters else 'default'
        city = user_filters.get('city') if user_filters else None
        min_price = int(user_filters.get('min_price')) if user_filters and user_filters.get('min_price') else None
        max_price = int(user_filters.get('max_price')) if user_filters and user_filters.get('max_price') else None
        rooms = int(user_filters.get('rooms')) if user_filters and user_filters.get('rooms') else None
        
        cities = [city] if city else CITIES.keys()
        
        for city in cities:
            ads = await ApartmentParser.fetch_ads(city, min_price, max_price, rooms)
            
            with sqlite3.connect("ads.db") as conn:
                cursor = conn.cursor()
                existing = set(row[0] for row in cursor.execute("SELECT link FROM ads").fetchall())
                new_ads = [ad for ad in ads if ad['link'] not in existing]
                
                if new_ads:
                    cursor.executemany("""
                        INSERT OR IGNORE INTO new_ads 
                        (link, source, city, price, rooms, address, image, description, user_id)
                        VALUES (:link, :source, :city, :price, :rooms, :address, :image, :description, ?)
                    """, [(user_id,)]*len(new_ads), new_ads)
                    
                    if user_id.isdigit():
                        message = f"Появилось {len(new_ads)} новых объявлений в {CITIES[city]}!"
                        asyncio.create_task(app.bot.send_message(chat_id=user_id, text=message))
                
                cursor.executemany("""
                    INSERT OR IGNORE INTO ads 
                    (link, source, city, price, rooms, address, image, description)
                    VALUES (:link, :source, :city, :price, :rooms, :address, :image, :description)
                """, ads)
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка в fetch_and_store_ads: {e}")

@app.route('/api/ads', methods=['GET'])
def get_ads():
    try:
        city = request.args.get('city')
        min_price = request.args.get('min_price', type=int)
        max_price = request.args.get('max_price', type=int)
        rooms = request.args.get('rooms', type=int)
        offset = request.args.get('offset', default=0, type=int)
        limit = request.args.get('limit', default=KUFAR_LIMIT, type=int)
        
        query = "SELECT * FROM ads WHERE 1=1"
        params = []
        
        if city:
            query += " AND city = ?"
            params.append(city)
        if min_price:
            query += " AND price >= ?"
            params.append(min_price)
        if max_price:
            query += " AND price <= ?"
            params.append(max_price)
        if rooms:
            query += " AND rooms = ?"
            params.append(rooms)
            
        with sqlite3.connect("ads.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query + " LIMIT ? OFFSET ?", params + [limit, offset])
            ads = [dict(row) for row in cursor.fetchall()]
            
            total = cursor.execute("SELECT COUNT(*) FROM ads" + query.split("SELECT *")[1], params).fetchone()[0]
            
            return jsonify({
                "ads": ads,
                "has_more": total > offset + limit,
                "total": total
            })
    except Exception as e:
        logger.error(f"Ошибка в /api/ads: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/submit_user_ad', methods=['POST'])
async def submit_user_ad():
    try:
        user_id = request.form.get('user_id')
        city = request.form.get('city')
        price = request.form.get('price')
        address = request.form.get('address')
        
        # Валидация обязательных полей
        if not all([user_id, city, price, address]):
            return jsonify({"error": "Missing required fields"}), 400
            
        images = request.files.getlist('images')
        image_paths = []
        
        for image in images[:5]:
            if image and image.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                filename = f"{uuid.uuid4()}_{image.filename}"
                path = os.path.join(UPLOAD_FOLDER, filename)
                image.save(path)
                image_paths.append(path)
                
        images_str = ','.join(image_paths) if image_paths else None
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with sqlite3.connect("ads.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_ads 
                (user_id, images, city, rooms, price, address, description, phone, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                images_str,
                city,
                request.form.get('rooms'),
                price,
                address,
                request.form.get('description'),
                request.form.get('phone'),
                timestamp
            ))
            ad_id = cursor.lastrowid
            conn.commit()
            
        message = f"""
            Новое объявление на модерацию (ID: {ad_id})
            Город: {CITIES.get(city, 'Неизвестный')}
            Цена: {price} USD
            Адрес: {address}
        """
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Одобрить", callback_data=f"approve_{ad_id}"),
             InlineKeyboardButton("Отклонить", callback_data=f"reject_{ad_id}")]
        ])
        
        await app.bot.send_message(chat_id=ADMIN_ID, text=message, reply_markup=keyboard)
        return jsonify({"status": "pending", "message": "Объявление отправлено на модерацию"})
    except Exception as e:
        logger.error(f"Ошибка в /api/submit_user_ad: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Остальные маршруты и классы остаются с аналогичными улучшениями...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)