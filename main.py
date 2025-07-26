import os
import uuid
import random
import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from headers import headers_list
from my_ip import ip_list


class SourceAddressAdapter(HTTPAdapter):
    """HTTPAdapter binding requests to a specific source IP."""

    def __init__(self, source_ip: str, **kwargs):
        self._source_ip = source_ip
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = (self._source_ip, 0)
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["source_address"] = (self._source_ip, 0)
        return super().proxy_manager_for(*args, **kwargs)


class SnappFoodCrawler:
    def __init__(self, vendor_file_path: str):
        """Initialize the crawler with a path to the vendor Excel file."""
        self.vendor_file = vendor_file_path
        self.vendors = []
        self.results = []

    def load_vendors(self):
        """Load vendor data from the Excel file."""
        df_vendors = pd.read_excel(self.vendor_file)
        self.vendors = df_vendors.to_dict(orient="records")
        print(f"Loaded {len(self.vendors)} vendors from '{self.vendor_file}'")

    @staticmethod
    def choose_headers():
        return random.choice(headers_list)

    @staticmethod
    def choose_ip():
        return random.choice(ip_list)

    def fetch_vendor_data(self, vendor: dict):
        vendor_id = vendor.get("vendor_id")
        vendor_code = vendor.get("vendor_code")
        lat = vendor.get("lat")
        lon = vendor.get("lon")

        if not vendor_code or lat is None or lon is None:
            print(
                f"Skipping vendor {vendor_id}: missing required data (code/lat/lon)"
            )
            return

        params = {
            "lat": lat,
            "long": lon,
            "optionalClient": "WEBSITE",
            "client": "WEBSITE",
            "deviceType": "WEBSITE",
            "appVersion": "8.1.1",
            "UDID": str(uuid.uuid4()),
            "vendorCode": str(vendor_code),
            "locationCacheKey": f"lat={lat}&long={lon}",
            "show_party": "1",
            "fetch-static-data": "1",
            "locale": "fa",
        }

        source_ip = self.choose_ip()
        headers = self.choose_headers()
        session = requests.Session()
        session.mount("http://", SourceAddressAdapter(source_ip))
        session.mount("https://", SourceAddressAdapter(source_ip))

        try:
            response = session.get(
                "https://snappfood.ir/mobile/v2/restaurant/details/dynamic",
                params=params,
                headers=headers,
                timeout=15,
            )
        except Exception as e:
            print(
                f"Request error for vendor {vendor_id} (code {vendor_code}) "
                f"with IP {source_ip}: {e}"
            )
            session.close()
            return

        if response.status_code != 200:
            print(
                f"Non-200 response for vendor {vendor_id} (code {vendor_code}): "
                f"HTTP {response.status_code}"
            )
            session.close()
            return

        try:
            data = response.json()
        except Exception as e:
            print(
                f"Failed to parse JSON for vendor {vendor_id} (code {vendor_code}): {e}"
            )
            session.close()
            return

        if not data.get("status"):
            print(
                f"No data returned for vendor {vendor_id} (code {vendor_code}), 'status' flag is False."
            )
            session.close()
            return

        vendor_data = data.get("data", {})
        if not vendor_data:
            print(
                f"No 'data' field in response for vendor {vendor_id} (code {vendor_code})."
            )
            session.close()
            return

        menus = vendor_data.get("menus", [])
        for menu in menus:
            category_id = menu.get("categoryId")
            category_title = menu.get("category")
            products = menu.get("products", [])

            for product in products:
                product_record = {
                    "vendor_id": vendor_id,
                    "vendor_product_id": product.get("id"),
                    "product_id": product.get("productId"),
                    "title": product.get("title"),
                    "price": product.get("price"),
                    "discount": product.get("discount"),
                    "discount_ratio": product.get("discountRatio"),
                    "product_title": product.get("productTitle"),
                    "product_variation": product.get("productVariationTitle"),
                    "category_id": category_id,
                    "category_title": category_title,
                    "image_id": None,
                    "image_path": None,
                }

                images = product.get("images", [])
                if images:
                    img_info = images[0]
                    image_id = img_info.get("imageId")
                    image_url = img_info.get("imageSrc")
                    if image_id and image_url:
                        vendor_dir = os.path.join("images", str(vendor_id))
                        os.makedirs(vendor_dir, exist_ok=True)
                        image_path = os.path.join(vendor_dir, f"{image_id}.jpg")
                        try:
                            img_res = session.get(image_url, timeout=10)
                            if img_res.status_code == 200:
                                with open(image_path, "wb") as f:
                                    f.write(img_res.content)
                            else:
                                print(
                                    f"Failed to download image {image_id} "
                                    f"(HTTP {img_res.status_code}) for vendor {vendor_id}"
                                )
                        except Exception as img_err:
                            print(
                                f"Error downloading image {image_id} for vendor {vendor_id}: {img_err}"
                            )
                        else:
                            product_record["image_id"] = image_id
                            product_record["image_path"] = image_path

                self.results.append(product_record)

        session.close()

    def run(self):
        self.load_vendors()
        if not self.vendors:
            print("No vendors to process. Please check the vendor file.")
            return

        for vendor in self.vendors:
            vid = vendor.get("vendor_id")
            vtitle = vendor.get("vendor_title", "N/A")
            print(f"Processing vendor {vid} - {vtitle}")
            self.fetch_vendor_data(vendor)

        if self.results:
            output_df = pd.DataFrame(self.results)
            output_file = "snappfood_vendor_products.xlsx"
            output_df.to_excel(output_file, index=False)
            print(f"\nSaved {len(self.results)} product records to '{output_file}'.")
        else:
            print("No product data collected to save.")


def main():
    vendor_excel = "snappfood_vendors.xlsx"
    crawler = SnappFoodCrawler(vendor_excel)
    crawler.run()


if __name__ == "__main__":
    main()
