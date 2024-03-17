import asyncio
import os
from enum import Enum
from typing import List, Tuple, Optional

import fastapi
import httpx
import uvicorn
from aiocache import cached
from dotenv import load_dotenv
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

app = fastapi.FastAPI()
app.mount("/static", StaticFiles(directory="./static"), name="static")

load_dotenv()
RIOT_API_KEY = os.getenv('RIOT_API_KEY')


class HistoryEntry(BaseModel):
    champion_name: str = '',
    champion_icon: str = '',
    items: List[Optional[str]] = [],
    kills: int = 0,
    deaths: int = 0,
    assists: int = 0,
    creep_score: int = 0,
    game_duration: int = 0,
    win: bool = False,
    game_mode: str = '',
    game_start: int = 0,


class GameRegion(str, Enum):
    BR = 'br1'
    EUNE = 'eun1'
    EUW = 'euw1'
    LAN = 'la1'
    LAS = 'la2'
    NA = 'na1'
    OCE = 'oc1'
    RU = 'ru1'
    TR = 'tr1'
    JP = 'jp1'
    KR = 'kr'
    PH = 'ph2'
    SG = 'sg2'
    TW = 'tw2'
    TH = 'th2'
    VN = 'vn2'


class GeneralRegion(str, Enum):
    AMERICAS = 'americas'
    ASIA = 'asia'
    EUROPE = 'europe'
    SEA = 'sea'


def get_general_region(game_region: GameRegion) -> GeneralRegion:
    match game_region:
        case GameRegion.NA | GameRegion.BR | GameRegion.LAN | GameRegion.LAS:
            return GeneralRegion.AMERICAS
        case GameRegion.KR | GameRegion.JP:
            return GeneralRegion.ASIA
        case GameRegion.EUNE | GameRegion.EUW | GameRegion.TR | GameRegion.RU:
            return GeneralRegion.EUROPE
        case _:
            return GeneralRegion.SEA


def key_builder(function, client, *args, **kwargs):
    return function, args


@cached(ttl=600, key_builder=key_builder)
async def fetch_account_dto(
        client: httpx.AsyncClient,
        region: str,
        nickname: str,
        tag: str,
):
    response = await client.get(
        f'https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{nickname}/{tag}'
    )
    response.raise_for_status()
    account_dto = response.json()
    return account_dto


@cached(ttl=60, key_builder=key_builder)
async def fetch_match_ids(
        client: httpx.AsyncClient,
        region: str,
        puuid: str,
):
    response = await client.get(
        f'https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids',
        params={
            'count': 10
        }
    )
    response.raise_for_status()
    match_ids = response.json()
    return match_ids


@cached(key_builder=key_builder)
async def fetch_match(
        client: httpx.AsyncClient,
        region: str,
        match_id: str,
):
    response = await client.get(
        f'https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
    )
    response.raise_for_status()
    match_dto = response.json()
    return match_dto


async def fetch_matches(
        client: httpx.AsyncClient,
        region: str,
        match_ids: List[str],
):
    tasks = [fetch_match(client, region, match_id) for match_id in match_ids]
    match_dtos = await asyncio.gather(*tasks)
    return match_dtos


@cached(ttl=600, key_builder=key_builder)
async def fetch_summoner_dto(
        client: httpx.AsyncClient,
        region: str,
        puuid: str,
):
    response = await client.get(
        f'https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}'
    )
    response.raise_for_status()
    summoner_dto = response.json()
    return summoner_dto


@cached(key_builder=key_builder)
async def fetch_items_json(client: httpx.AsyncClient):
    response = await client.get(
        'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/items.json'
    )
    response.raise_for_status()
    items = response.json()
    return items


async def fetch_item_icon_url(
        client: httpx.AsyncClient,
        item_id: int,
):
    items = await fetch_items_json(client)
    url = None
    try:
        for item in items:
            if item['id'] == item_id:
                url = item['iconPath'].replace(
                    '/lol-game-data/assets/',
                    'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/'
                ).lower()
                break
    finally:
        return url


def fetch_champion_icon_url(champion_id: int):
    return f'https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/{champion_id}.png'


async def convert_match_dto(client: httpx.AsyncClient, match_dto, puuid) -> HistoryEntry:
    history_entry = HistoryEntry()

    try:
        info_dto = match_dto['info']
        for participant_dto in info_dto['participants']:
            if participant_dto['puuid'] == puuid:
                break

        history_entry.champion_name = participant_dto['championName']
        history_entry.champion_icon = fetch_champion_icon_url(participant_dto['championId'])

        item_ids = [participant_dto[f'item{i}'] for i in range(7)]
        item_tasks = [fetch_item_icon_url(client, item_id) for item_id in item_ids]
        history_entry.items = await asyncio.gather(*item_tasks)

        history_entry.kills = participant_dto['kills']
        history_entry.deaths = participant_dto['deaths']
        history_entry.assists = participant_dto['assists']
        history_entry.creep_score = participant_dto['totalMinionsKilled']
        history_entry.game_duration = info_dto['gameDuration']
        history_entry.win = participant_dto['win']
        history_entry.game_mode = info_dto['gameMode']
        history_entry.game_start = info_dto['gameStartTimestamp']
    finally:
        return history_entry


async def convert_match_dtos(client: httpx.AsyncClient, match_dtos, puuid) -> Tuple[HistoryEntry]:
    tasks = [convert_match_dto(client, match_dto, puuid) for match_dto in match_dtos]
    return await asyncio.gather(*tasks)


@app.get("/history")
async def history(
        region: GameRegion,
        nickname: str,
        tag: str,
) -> List[HistoryEntry]:
    general_region = get_general_region(region).value

    try:
        async with httpx.AsyncClient(headers={'X-Riot-Token': RIOT_API_KEY}) as client:
            account_dto = await fetch_account_dto(client, GeneralRegion.EUROPE.value, nickname, tag)
            match_ids = await fetch_match_ids(client, general_region, account_dto['puuid'])
            match_dtos = await fetch_matches(client, general_region, match_ids)
            history_entries = await convert_match_dtos(client, match_dtos, account_dto['puuid'])
            return list(history_entries)
    except httpx.RequestError as e:
        print(e)
        raise fastapi.HTTPException(502, detail="Could not fetch upstream data")
    except httpx.HTTPStatusError as e:
        print(e)
        raise fastapi.HTTPException(e.response.status_code, detail="Upstream returned an error")
    except Exception as e:
        print(e)
        raise fastapi.HTTPException(500, detail="Internal server error")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
