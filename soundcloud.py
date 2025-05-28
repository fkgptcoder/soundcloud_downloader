import requests
import re
import time
import io
from typing import List
from pydub import AudioSegment


BASE_URL = "https://api-v2.soundcloud.com"
RESOLVE_URL = "https://api-widget.soundcloud.com/resolve"
FIREFOX_VERSION_URL = "https://product-details.mozilla.org/1.0/firefox_versions.json"
APP_VERSION_URL = "https://soundcloud.com/versions.json"


class Soundcloud:
    def __init__(self, o_auth: str, client_id: str):
        if len(client_id) != 32:
            raise ValueError("Client_IDの形式が間違っています。")
        
        self.client_id = client_id
        self.o_auth = o_auth
        self.app_version = self._fetch_app_version()
        self.headers = {
            "Authorization": o_auth,
            "Accept": "application/json",
            "User-Agent": self._get_firefox_user_agent()
        }

    def _get_firefox_user_agent(self) -> str:
        firefox_versions = requests.get(FIREFOX_VERSION_URL).json()
        version = firefox_versions.get('LATEST_FIREFOX_VERSION', '120.0')
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}) Gecko/20100101 Firefox/{version}"

    def _fetch_app_version(self) -> str:
        app_info = requests.get(APP_VERSION_URL).json()
        return app_info.get('app', '')

    def _combine_mp3s(self, mp3_files: List[io.BytesIO], output_path: str) -> None:
        combined = AudioSegment.empty()
        for mp3_file in mp3_files:
            mp3_file.seek(0)
            combined += AudioSegment.from_file(mp3_file, format="mp3")
        combined.export(output_path, format="mp3")

    def _retry_get_json(self, url: str, max_retries: int = 5, delay: float = 1.0):
        for _ in range(max_retries):
            try:
                response = requests.get(url)
                if response.ok:
                    return response.json()
            except Exception:
                pass
            time.sleep(delay)
        raise Exception(f"Failed to get valid JSON from {url}")

    def download(self, link: str, output_file: str = "test.mp3") -> None:
        if "utm_source" in link:
            link = re.sub(r'\?.*', '', link)

        resolve_url = f"{RESOLVE_URL}?url={link}&format=json&client_id={self.client_id}&app_version={self.app_version}"
        resolve_data = self._retry_get_json(resolve_url)
        track_id = resolve_data["id"]
        track_auth = resolve_data["track_authorization"]
        uuid_match = re.search(r'/([^/]+)/stream', resolve_data['media']['transcodings'][0]['url'])
        if not uuid_match:
            raise ValueError("トラックのUUIDが見つかりませんでした。")
        uuid = uuid_match.group(1)

        hls_url = (
            f"{BASE_URL}/media/soundcloud:tracks:{track_id}/{uuid}/stream/hls"
            f"?client_id={self.client_id}&track_authorization={track_auth}"
        )

        hls_data = self._retry_get_json(hls_url)
        playlist_url = hls_data["url"]

        playlist_content = requests.get(playlist_url).content.decode()
        segment_urls = re.findall(r'https?://[^\s]+', playlist_content)

        mp3_segments = []
        for url in segment_urls:
            response = requests.get(url)
            if response.ok:
                mp3_segments.append(io.BytesIO(response.content))

        self._combine_mp3s(mp3_segments, output_file)
