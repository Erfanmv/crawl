#!/usr/bin/env python3
"""
crawl/main.py
Final: 6-decimal URL, Brotli-safe JSON, 415-free image download,
retries & polite delays.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from headers import headers_list
from my_ip import ip_list

# optional Brotli
try:
    import brotli as _brotli
    BROTLI_OK = True
except ModuleNotFoundError:
    _brotli = None
    BROTLI_OK = False


# -----------------------------------------------------------------------------#
class SourceIPAdapter(HTTPAdapter):
    def __init__(self, src_ip: str) -> None:
        self._src_addr = (src_ip, 0)
        retry = Retry(total=2, backoff_factor=0.3,
                      status_forcelist=[502, 503, 504])
        super().__init__(max_retries=retry)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = self._src_addr
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["source_address"] = self._src_addr
        return super().proxy_manager_for(*args, **kwargs)


# -----------------------------------------------------------------------------#
class SnappFoodCrawler:
    URL_TMPL = (
        "https://snappfood.ir/mobile/v2/restaurant/details/dynamic?"
        "lat={lat}&long={lon}&optionalClient=WEBSITE&client=WEBSITE&deviceType=WEBSITE&"
        "appVersion=8.1.1&UDID=afc6e8a9-e6af-4940-ba31-0ff2fe96830d&"
        "vendorCode={vendor_code}&locationCacheKey=lat%3D{lat}%26long%3D{lon}&"
        "show_party=1&fetch-static-data=1&locale=fa"
    )

    def __init__(
        self,
        vendor_file: str = "snappfood_vendors.xlsx",
        vendor_delay: tuple[float, float] = (1.0, 2.0),
        product_delay: float = 0.2,
        max_attempts: int = 3,
        verbose: bool = False,
    ) -> None:
        self.vendor_file = vendor_file
        self.vendor_delay = vendor_delay
        self.product_delay = product_delay
        self.max_attempts = max_attempts
        self.verbose = verbose
        self.vendors: List[Dict[str, Any]] = []
        self.records: List[Dict[str, Any]] = []

    # ----------------------------- sessions --------------------------------- #
    def _session(self, ip: str, hdr: Dict[str, str]) -> requests.Session:
        s = requests.Session()
        s.mount("http://", SourceIPAdapter(ip))
        s.mount("https://", SourceIPAdapter(ip))
        s.headers.update(hdr)
        return s

    # ----------------------------- image DL --------------------------------- #
    def _download(self, url: str, vendor_id: int, img_id: str,
                  ref_session: requests.Session) -> Optional[Path]:
        dest = Path("images") / str(vendor_id) / f"{img_id}.jpg"
        if dest.exists():
            return dest
        img_headers = {
            "User-Agent": ref_session.headers.get("User-Agent", "Mozilla/5.0"),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        try:
            with requests.Session() as s:
                s.headers.update(img_headers)
                r = s.get(url, timeout=10, stream=True)
                r.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as fh:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            fh.write(chunk)
            return dest
        except Exception as exc:
            print(f"      ↳ image download failed: {exc}")
            return None

    # --------------------------- JSON helpers ------------------------------ #
    def _decode_json(self, res: requests.Response,
                     vid: int, attempt: int, ip: str) -> Optional[dict]:
        # 1) normal
        try:
            return res.json()
        except ValueError:
            pass

        enc = res.headers.get("Content-Encoding", "").lower()
        # 2) manual Brotli
        if "br" in enc:
            if not BROTLI_OK:
                print(f"[{vid}] attempt {attempt} via {ip} → Brotli body but "
                      f"'brotli' module not installed")
                return None
            try:
                raw = _brotli.decompress(res.content)
                return json.loads(raw)
            except Exception as exc:
                print(f"[{vid}] attempt {attempt} via {ip} → manual Brotli "
                      f"decompress failed: {exc}")
                return None
        # 3) UTF-8 fallback
        try:
            text = res.content.decode("utf-8", errors="replace")
            return json.loads(text)
        except Exception:
            snippet = res.text[:120].replace("\n", " ")
            print(f"[{vid}] attempt {attempt} via {ip} → failed to parse "
                  f"JSON | {snippet!r}")
            return None

    # --------------------------- workflow ---------------------------------- #
    def load_vendors(self) -> None:
        df = pd.read_excel(self.vendor_file, engine="openpyxl")
        need = {"vendor_id", "vendor_code", "lat", "lon"}
        if not need.issubset(df.columns):
            raise ValueError(f"Vendor file missing columns: {need - set(df.columns)}")
        self.vendors = df.to_dict(orient="records")
        print(f"Loaded {len(self.vendors)} vendors\n")

    def _try_request(self, vid: int, vcode: str, lat: float, lon: float) -> Optional[dict]:
        for attempt in range(1, self.max_attempts + 1):
            ip  = random.choice(ip_list)
            hdr = random.choice(headers_list).copy()
            if attempt > 1 and "Authorization" in hdr:
                hdr.pop("Authorization")
            sess = self._session(ip, hdr)
            url = self.URL_TMPL.format(
                lat=f"{lat:.6f}", lon=f"{lon:.6f}", vendor_code=vcode,
            )
            if self.verbose:
                print(f"[DEBUG] v{vid} a{attempt} url → {url}")

            try:
                res = sess.get(url, timeout=15)
            except Exception as exc:
                print(f"[{vid}] attempt {attempt}/{self.max_attempts} net-err via {ip}: {exc}")
                continue
            if res.status_code != 200:
                snippet = res.text[:100].replace("\n", " ")
                print(f"[{vid}] attempt {attempt} via {ip} → HTTP {res.status_code} | {snippet!r}")
                continue
            data = self._decode_json(res, vid, attempt, ip)
            if data is not None:
                return data
        return None

    def _process_product(self, sess: requests.Session, prod: Dict[str, Any],
                         vendor_id: int, cat_id: Optional[int], cat_title: str):
        vp_id = prod.get("id")
        p_id  = prod.get("productId")
        base  = prod.get("productTitle") or prod.get("title", "")
        var   = prod.get("productVariationTitle") or ""
        title = f"{base} {var}".strip()

        images = prod.get("images") or []
        first_id, first_path = None, None
        for img in images:
            img_id  = img.get("imageId") or uuid.uuid4().hex
            img_url = img.get("imageSrc") or img.get("url")
            if not img_url:
                continue
            saved = self._download(img_url, vendor_id, img_id, sess)
            if first_id is None and saved:
                first_id, first_path = img_id, str(saved)

        self.records.append({
            "vendor_id": vendor_id,
            "vendor_product_id": vp_id,
            "product_id": p_id,
            "title": title,
            "price": prod.get("price"),
            "discount": prod.get("discount", 0),
            "discount_ratio": prod.get("discountRatio", 0),
            "product_title": base,
            "product_variation": var,
            "category_id": cat_id,
            "category_title": cat_title,
            "image_id": first_id,
            "image_path": first_path,
        })

    def run(self) -> None:
        self.load_vendors()
        t0 = time.time()

        for idx, v in enumerate(self.vendors, 1):
            vid, vcode, lat, lon = v["vendor_id"], v["vendor_code"], v["lat"], v["lon"]
            print(f"[{idx}/{len(self.vendors)}] vendor {vid} ({vcode})")

            payload = self._try_request(vid, vcode, lat, lon)
            if not payload or not payload.get("status"):
                print(f"[{vid}] skipped – no success\n")
                time.sleep(random.uniform(*self.vendor_delay))
                continue

            menus = payload.get("data", {}).get("menus", [])
            if not menus:
                print(f"[{vid}] no menus\n")
                time.sleep(random.uniform(*self.vendor_delay))
                continue

            sess = self._session(random.choice(ip_list), random.choice(headers_list))
            for menu in menus:
                cid, ctit = menu.get("categoryId"), menu.get("category", "")
                for prod in menu.get("products", []):
                    self._process_product(sess, prod, vid, cid, ctit)
                    time.sleep(self.product_delay)

            print(f"[{vid}] done – total products so far {len(self.records)}\n")
            time.sleep(random.uniform(*self.vendor_delay))

        if not self.records:
            print("No products collected.")
            return

        df = pd.DataFrame(self.records)
        cols = [
            "vendor_id", "vendor_product_id", "product_id", "title", "price",
            "discount", "discount_ratio", "product_title", "product_variation",
            "category_id", "category_title", "image_id", "image_path",
        ]
        df = df[cols]
        df.to_excel("snappfood_vendor_products.xlsx", index=False, engine="openpyxl")
        print(f"\nSaved {len(df)} rows → snappfood_vendor_products.xlsx  "
              f"({time.time()-t0:.1f}s)")


# -----------------------------------------------------------------------------#
if __name__ == "__main__":
    crawler = SnappFoodCrawler(
        vendor_file="snappfood_vendors.xlsx",
        vendor_delay=(1.0, 2.0),
        product_delay=0.2,
        max_attempts=3,
        verbose=False,
    )
    crawler.run()
