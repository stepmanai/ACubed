import asyncio
import time

from acubed.connector import FFRDatabaseConnectorOptimized

if __name__ == "__main__":
    config = {"username": "wirrywoo", "password": "556d4cbd8bdab43fdaa6b900614de69d"}

    start_time = time.time()
    print("--- Downloading Charts from FFR API Source ---")

    connector = FFRDatabaseConnectorOptimized(config)
    asyncio.run(connector.run())

    print(f"--- Downloaded {len(connector.charts)} Charts: {time.time() - start_time:.2f} seconds ---")
