import requests
from config import logger, headers, url
from typing import List, Dict


def connect_to_api() -> List[Dict]:
    """
    Connects to an API to fetch stock market data for a predefined list of stocks.

    Sends HTTP GET requests to the API for each stock in the `stocks` list
    and collects the response data in JSON format. It handles errors and logs the progress.

    Returns:
        List[Dict]: A list of JSON responses for each stock containing the stock's 
                    time-series intraday data.

    Example:
        response = connect_to_api()
    """

    stocks = ['KOS', 'TROX', 'WTI', 'AAPL', 'TSLA']
    json_response = []

    for stock in range(0, len(stocks)):
        querystring = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": f"{stocks[stock]}",
            "outputsize": "compact",
            "interval": "5min",
            "datatype": "json"
        }

        try:
            response = requests.get(url, headers=headers, params=querystring)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Stocks {stocks[stock]} loaded successfully")

            json_response.append(data)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error on stock: {e}")
            break

    return json_response


def extract_json(response: List[Dict]) -> List[Dict[str, str]]:
    """
    Extracts relevant stock data from the API response JSON and formats it into a list of records.

    Processes the JSON response returned by `connect_to_api()` and extracts
    stock data such as the symbol, date, open, close, high, and low prices, and returns
    a formatted list of records.

    Args:
        response (List[Dict]): The JSON response data from the API call.

    Returns:
        List[Dict[str, str]]: A list of dictionaries containing the stock data with 
                               keys like "symbol", "date", "open", "close", "high", and "low".

    Example:
        formatted_data = extract_json(response)
    """

    records = []

    for data in response:
        symbol = data['Meta Data']['2. Symbol']

        for date_str, metrics in data['Time Series (5min)'].items():
            record = {
                "symbol": symbol,
                "date": date_str,
                "open": metrics["1. open"],
                "close": metrics["4. close"],
                "high": metrics["2. high"],
                "low": metrics["3. low"]
            }

            records.append(record)

    return records