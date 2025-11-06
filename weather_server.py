import json
import httpx
from typing import Any

from mcp.server.fastmcp import FastMCP 


mcp = FastMCP("WeatherServer")

OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5/weather"
API_KEY = "09ac42f5c9a4b1f2870db69bf2ccd4c9"
USER_AGEHT = "weather-app/1.0"

async def fetch_weather(city:str)->dict[str,Any] | None:
    """
    Obtain weather information from OpenWeather API
    :param city: 城市名称(需要使用英文,如Beijing)
    :return 天气数据字典;若出错,返回包含error 信息的字典
    """
    params = {
        "q":city,
        "appid":API_KEY,
        "units":"metric",
        "lang":"zh_cn"
    }
    headers = {"User-Agent":USER_AGEHT}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(OPENWEATHER_API_BASE, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error":f"HTTP error:{e.response.status_code}"}
        except Exception as e:
            return {"error":f"请求失败：{str(e)}"}


def format_weather(data:dict[str,Any]|str)->str:
    """
    将天气数据格式化为易读文本。
    """
    if isinstance(data,str):
        try:
            data = json.loads(data)
        except Exception as e:
            return f"无法解析天气数据：{e}"
    
    if "error" in data:
        return f"{data['error']}"

    city = data.get("name","未知")
    country = data.get("sys",{}).get("country","未知")
    temp = data.get("main",{}).get("temp","N/A")
    humidity = data.get("main",{}).get("humidity","N/A")
    wind_speed = data.get("wind",{}).get("speed","N/A")
    weather_list = data.get("weather",[{}])
    description = weather_list[0].get("description","未知")

    return (
        f"{city}, {country}\n"
        f"温度:{temp}摄氏度\n"
        f"湿度:{humidity}\n"
        f"风速:{wind_speed}m/s\n"
        f"天气:{description}\n"
    )

@mcp.tool()
async def query_weather(city:str)->str:
    """
    Input the english name of the city, return the weather result of today
    :param city: 城市名称(需要使用英文)
    :return:格式化后的天气信息
    """
    data = await fetch_weather(city)
    return format_weather(data)

if __name__ == "__main__":
    mcp.run(transport='stdio')
