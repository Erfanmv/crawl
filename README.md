# SnappFood Vendor Pricing Crawler

This project contains a simple crawler that fetches vendor menu data from the
SnappFood API. Vendors are loaded from an Excel file and each request is sent
using a random source IP and HTTP headers to better mimic real traffic. Product
images are downloaded locally and the final results are exported to an Excel
file.

## Files

- **main.py** – implements the `SnappFoodCrawler` class and provides a command
  line entry point.
- **headers.py** – a list of HTTP headers used for requests. Update the bearer
  token if the API requires authentication.
- **my_ip.py** – list of IP addresses available for use as the source address.
- **images/** – directory where product images will be stored (created at
  runtime).

To run the crawler, prepare an Excel file named `snappfood_vendors.xlsx`
containing the columns `vendor_id`, `vendor_code`, `lat` and `lon` (and optional
`vendor_title`). Then execute:

```bash
python main.py
```

At the end of the run the file `snappfood_vendor_products.xlsx` will be created
with all collected product data.
