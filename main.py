# https://github.com/grahamwaters/LittleJohn_rh.git
import logging
import pandas as pd
import pandas_ta as ta
from robin_stocks import robinhood as r
from datetime import datetime
from pytz import timezone
import asyncio
from legacy.V5.main2 import stop_loss_percent
from tqdm import tqdm
from colorama import Fore, Style
class Utility:
    def __init__(self):
        pass
    async def log_file_size_checker():
        while True:
            #ic()
            with open('logs/robinhood.log', 'r') as f:
                lines = f.readlines()
                if len(lines) > 1000: # if the log file is greater than 1000 lines
                    # find how many lines to remove
                    num_lines_to_remove = len(lines) - 1000
                    # remove the first num_lines_to_remove lines
                    with open('logs/robinhood.log', 'w') as f:
                        f.writelines(lines[num_lines_to_remove:])
            await asyncio.sleep(1200)



    def get_last_100_days(self, coin):
        try:
            df = pd.DataFrame(r.crypto.get_crypto_historicals(coin, interval='hour', span='3month', bounds='24_7'))
            df = df.set_index('begins_at')
            df.index = pd.to_datetime(df.index)
            df = df.loc[:, ['close_price', 'open_price', 'high_price', 'low_price']]
            df = df.rename(columns={'close_price': 'close', 'open_price': 'open', 'high_price': 'high', 'low_price': 'low'})
            df = df.apply(pd.to_numeric)
            return df
        except Exception as e:
            print(f'Unable to get data for {coin}... {e}')
            return pd.DataFrame()
    def is_daytime(self):
        current_time = datetime.now(timezone('US/Central'))
        current_hour = current_time.hour
        if current_hour >= 8 and current_hour <= 20:
            return True
        else:
            return False
class Trader:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        # Set up logging
        self.logger = logging.getLogger('trader')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        # Login to Robinhood
        self.login_setup()
    def login_setup(self):
        try:
            r.login(self.username, self.password)
            self.logger.info('Logged in to Robinhood successfully.')
        except Exception as e:
            self.logger.error(f'Unable to login to Robinhood... {e}')
    def resetter(self):
        try:
            open_orders = r.get_all_open_crypto_orders()
            print(Fore.YELLOW + 'Canceling all open orders...' + Style.RESET_ALL)
            for order in tqdm(open_orders):
                r.cancel_crypto_order(order['id'])
            print(Fore.GREEN + 'All open orders cancelled.')
            self.logger.info('All open orders cancelled.' + Style.RESET_ALL)
            crypto_positions = r.get_crypto_positions()
            for position in crypto_positions:
                r.order_sell_crypto_limit(position['currency']['code'], position['quantity'], position['cost_bases'][0]['direct_cost_basis'])
            self.logger.info('All positions sold.')
        except Exception as e:
            self.logger.error(f'Unable to reset orders and positions... {e}')
    def calculate_ta_indicators(self, coins):
        try:
            utility = Utility()
            signals_df = pd.DataFrame()
            for coin in coins:
                df = utility.get_last_100_days(coin)
                df['sma'] = df.close.rolling(window=50).mean()
                df['ema'] = df.close.ewm(span=50, adjust=False).mean()
                df['macd_line'], df['signal_line'], df['macd_hist'] = ta.macd(df.close)
                df['rsi'] = ta.rsi(df.close)
                df['williams'] = ta.williams_r(df.high, df.low, df.close)
                df['stochastic_k'], df['stochastic_d'] = ta.stoch(df.high, df.low, df.close)
                df['bollinger_l'], df['bollinger_m'], df['bollinger_u'] = ta.bollinger_bands(df.close)
                df['buy_signal'] = ((df.macd_line > df.signal_line) & (df.rsi < 30)) | ((df.stochastic_k > df.stochastic_d) & (df.williams < -80))
                df['sell_signal'] = ((df.macd_line < df.signal_line) & (df.rsi > 70)) | ((df.stochastic_k < df.stochastic_d) & (df.williams > -20))
                signals_df = signals_df.append(df)
            return signals_df
        except Exception as e:
            self.logger.error(f'Unable to generate trading signals... {e}')
            return pd.DataFrame()
    def trading_function(self, signals_df):
        try:
            crypto_positions = r.get_crypto_positions()
            for index, row in signals_df.iterrows():
                if row['buy_signal']:
                    #* Create a nice little data viz block for the terminal that shows the TA indicators for why this position was bought
                    block_text = f"""
                    {row['coin']} bought at {row['close']} because:
                    - MACD Line: {row['macd_line']}
                    - Signal Line: {row['signal_line']}
                    - RSI: {row['rsi']}
                    - Williams %R: {row['williams']}
                    - Stochastic K: {row['stochastic_k']}
                    - Stochastic D: {row['stochastic_d']}
                    """
                    print(Fore.GREEN + block_text + Style.RESET_ALL)
                    # Check if we have enough buying power to buy this coin
                    buying_power = self.update_buying_power()
                    if buying_power > 0:
                        r.order_buy_crypto_limit(symbol=row['coin'],
                                                    quantity = buying_power / row['close'],
                                                    limitPrice = row['close'],
                                                    timeInForce = 'gtc')
                        self.logger.info(f'Bought {row["coin"]} at {row["close"]}.')
                if row['sell_signal']:
                    for position in crypto_positions:
                        #* Create a nice little data viz block for the terminal that shows the TA indicators for why this position was sold
                        block_text = f"""
                        {row['coin']} sold at {row['close']} because:
                        - MACD Line: {row['macd_line']}
                        - Signal Line: {row['signal_line']}
                        - RSI: {row['rsi']}
                        - Williams %R: {row['williams']}
                        - Stochastic K: {row['stochastic_k']}
                        - Stochastic D: {row['stochastic_d']}
                        """
                        print(Fore.RED + block_text + Style.RESET_ALL)
                        if position['currency']['code'] == row['coin']:
                            r.order_sell_crypto_limit(symbol=row['coin'],
                                                        quantity=position['quantity'],
                                                        limitPrice=row['close'],
                                                        timeInForce='gtc')
                            self.logger.info(f'Sold {row["coin"]} at {row["close"]}.')
        except Exception as e:
            self.logger.error(f'Unable to execute trades... {e}')
    def get_total_crypto_dollars(self):
        try:
            crypto_positions = r.get_crypto_positions()
            total_crypto_dollars = 0
            for position in crypto_positions:
                total_crypto_dollars += float(position['quantity']) * float(r.crypto.get_crypto_quote(position['currency']['code'])['mark_price'])
            return total_crypto_dollars
        except Exception as e:
            self.logger.error(f'Unable to get total value of crypto... {e}')
            return 0
    def update_buying_power(self):
        try:
            profile_info = r.load_account_profile()
            cash_available = float(profile_info['cash_available_for_withdrawal'])
            crypto_dollars = self.get_total_crypto_dollars()
            buying_power = cash_available + crypto_dollars
            return buying_power
        except Exception as e:
            self.logger.error(f'Unable to update buying power... {e}')
            return 0
    def check_stop_loss_prices(self, coins, stop_loss_prices):
        try:
            for coin in tqdm(coins):
                current_price = float(r.crypto.get_crypto_quote(coin)['mark_price'])
                if current_price < stop_loss_prices[coin]:
                    crypto_positions = r.get_crypto_positions()
                    for position in crypto_positions:
                        if position['currency']['code'] == coin:
                            # r.orders.crypto(
                            # )
                            r.order_sell_crypto_limit(coin, position['quantity'], current_price)
                            self.logger.info(f'Sold {coin} at {current_price} due to stop loss.')
        except Exception as e:
            self.logger.error(f'Unable to check stop loss prices... {e}')
    def main(self, coins, stop_loss_prices):
        try:
            utility = Utility()
            if utility.is_daytime():
                self.resetter()
                signals_df = self.calculate_ta_indicators(coins)
                self.trading_function(signals_df)
                self.check_stop_loss_prices(coins, stop_loss_prices)
            else:
                self.logger.info('It is not daytime. The main function will not run.')
        except Exception as e:
            self.logger.error(f'Unable to run main function... {e}')
class Looper:
    def __init__(self, trader: Trader):
        self.trader = trader
        # Set up logging
        self.logger = logging.getLogger('looper')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    async def log_file_size_checker(self):
        pass
    async def run_async_functions(self, loop_count, coins, stop_loss_prices):
        try:
            if loop_count % 10 == 0:
                self.trader.update_buying_power()
            self.trader.main(coins, stop_loss_prices)
            # run all async functions simultaneously
            # log_file_size_checker included to prevent log file from getting too large
            self.trader.log_file_size_checker()
        except Exception as e:
            self.logger.error(f'Unable to run async functions... {e}')
    async def main_looper(self, coins, stop_loss_prices):
        loop_count = 0
        while True:
            try:
                await self.run_async_functions(loop_count, coins, stop_loss_prices)
                loop_count += 1
                await asyncio.sleep(3600)  # Sleep for an hour
            except Exception as e:
                self.logger.error(f'Error in main loop... {e}')
# run the program
if __name__ == '__main__':
    stop_loss_percent = 0.05 #^ set the stop loss percent at 5% (of the invested amount)
    coins = ['BTC', 'ETH', 'DOGE', 'SHIB', 'ETC', 'UNI', 'AAVE', 'LTC', 'LINK', 'COMP', 'USDC', 'AVAX', 'XLM', 'BCH', 'XTZ']
    #^ set stop losses for each coin by multiplying the current price by the stop loss percent (0.05) and subtracting that from the current price (to get the stop loss price).
    trader = Trader() #^ create an instance of the Trader class
    looper = Looper(trader) #^ create an instance of the Looper class (which will run the Trader class)
    stop_loss_prices = {coin: float(r.crypto.get_crypto_quote(coin)['mark_price']) - (float(r.crypto.get_crypto_quote(coin)['mark_price']) * stop_loss_percent) for coin in coins}
    print(f'Stop loss prices: {stop_loss_prices}')
    asyncio.run(looper.main_looper(coins, stop_loss_prices)) #^ run the main_looper function