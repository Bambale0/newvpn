import aiohttp
import json
import base64
import uuid
from datetime import datetime
from typing import Optional, Dict

class XrayManager:
    def __init__(self, panel_url: str, username: str, password: str):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session_cookie = None
        self.inbound_id = 1  # ID inbound в 3X-UI (обычно 1)
    
    async def _login(self) -> bool:
        """Авторизация в панели 3X-UI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.panel_url}/login",
                    data={"username": self.username, "password": self.password}
                ) as resp:
                    if resp.status == 200:
                        self.session_cookie = resp.cookies.get('session').value
                        return True
                    return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    async def _api_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """API запрос к панели"""
        if not self.session_cookie:
            if not await self._login():
                return None
        
        headers = {"Content-Type": "application/json"}
        cookies = {"session": self.session_cookie}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.panel_url}/panel/api/{endpoint}"
                
                if method == "GET":
                    async with session.get(url, headers=headers, cookies=cookies) as resp:
                        return await resp.json()
                elif method == "POST":
                    async with session.post(url, json=data, headers=headers, cookies=cookies) as resp:
                        return await resp.json()
        except Exception as e:
            print(f"API request error: {e}")
            return None
    
    async def create_client(self, email: str, expiry_date: datetime) -> Optional[Dict]:
        """
        Создание нового клиента в 3X-UI
        Возвращает client_id и ссылку на конфиг
        """
        client_id = str(uuid.uuid4())
        
        # Конвертируем дату в timestamp (миллисекунды)
        expiry_timestamp = int(expiry_date.timestamp() * 1000)
        
        client_data = {
            "id": self.inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": "xtls-rprx-vision",
                    "email": email,
                    "limitIp": 5,  # Макс. 5 устройств
                    "totalGB": 0,  # 0 = безлимит
                    "expiryTime": expiry_timestamp,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            })
        }
        
        result = await self._api_request("POST", "inbounds/addClient", client_data)
        
        if result and result.get("success"):
            # Получаем ссылку на подписку
            sub_link = await self._get_subscription_link(client_id, email)
            
            return {
                "id": client_id,
                "email": email,
                "config_link": sub_link
            }
        return None
    
    async def update_client_expiry(self, client_id: str, new_expiry: datetime, enable: bool = True) -> bool:
        """
        Обновление срока действия клиента (продление)
        Включает клиента если он был отключен
        """
        expiry_timestamp = int(new_expiry.timestamp() * 1000)
        
        # Получаем текущие данные клиента
        client_data = await self._get_client_data(client_id)
        if not client_data:
            return False
        
        update_data = {
            "id": self.inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": client_data.get("flow", "xtls-rprx-vision"),
                    "email": client_data.get("email", ""),
                    "limitIp": client_data.get("limitIp", 5),
                    "totalGB": client_data.get("totalGB", 0),
                    "expiryTime": expiry_timestamp,
                    "enable": enable,
                    "tgId": client_data.get("tgId", ""),
                    "subId": client_data.get("subId", "")
                }]
            })
        }
        
        result = await self._api_request("POST", "inbounds/updateClient/" + client_id, update_data)
        return result and result.get("success")
    
    async def disable_client(self, client_id: str) -> bool:
        """Отключение клиента (истечение подписки)"""
        client_data = await self._get_client_data(client_id)
        if not client_data:
            return False
        
        client_data["enable"] = False
        
        update_data = {
            "id": self.inbound_id,
            "settings": json.dumps({"clients": [client_data]})
        }
        
        result = await self._api_request("POST", "inbounds/updateClient/" + client_id, update_data)
        return result and result.get("success")
    
    async def _get_client_data(self, client_id: str) -> Optional[Dict]:
        """Получение данных клиента из панели"""
        result = await self._api_request("GET", f"inbounds/get/{self.inbound_id}")
        if result and result.get("success"):
            settings = json.loads(result["obj"]["settings"])
            for client in settings.get("clients", []):
                if client["id"] == client_id:
                    return client
        return None
    
    async def _get_subscription_link(self, client_id: str, email: str) -> str:
        """Генерация ссылки на подписку"""
        # Ссылка для импорта в приложения
        # Формат: vless://uuid@server:port?params#remark
        
        # Получаем настройки inbound
        result = await self._api_request("GET", f"inbounds/get/{self.inbound_id}")
        if not result or not result.get("success"):
            return "Ошибка генерации ссылки"
        
        inbound = result["obj"]
        stream_settings = json.loads(inbound.get("streamSettings", "{}"))
        
        # Параметры подключения (замените на свои)
        server = "your-server.com"  # Домен или IP сервера
        port = inbound.get("port", 443)
        protocol = inbound.get("protocol", "vless")
        
        # Параметры безопасности
        security = stream_settings.get("security", "tls")
        network = stream_settings.get("network", "tcp")
        
        # Формируем ссылку VLESS
        if protocol == "vless":
            params = f"type={network}&security={security}"
            if security == "tls" or security == "xtls":
                params += f"&sni={server}"
            
            config = f"{protocol}://{client_id}@{server}:{port}?{params}#{email}"
            return config
        
        return "Неподдерживаемый протокол"
    
    async def get_traffic_stats(self, client_id: str) -> Dict:
        """Получение статистики трафика клиента"""
        result = await self._api_request("GET", f"inbounds/getClientTraffics/{self.inbound_id}")
        if result and result.get("success"):
            for traffic in result.get("obj", []):
                if traffic.get("id") == client_id:
                    return {
                        "up": traffic.get("up", 0),
                        "down": traffic.get("down", 0),
                        "total": traffic.get("total", 0)
                    }
        return {"up": 0, "down": 0, "total": 0}
