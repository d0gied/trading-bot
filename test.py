import asyncio
import datetime
import time

from loguru import logger
from trading.client import InvestClient, get_client
from trading.transaction import Transaction
from trading.strategies import tick
from matplotlib import pyplot as plt


base_price = 200
price_step = 0.01  # 1%
limit_orders = []

last_price = base_price


def find_orders(from_, to):
    global limit_orders
    new_orders = []
    for order in limit_orders:
        if from_ <= order and order <= to:
            new_orders.append(order)
    return new_orders


def build_zones(price):
    zone_size = price * price_step

    plus_base = price + zone_size / 2
    for i in range(5):
        zone_down = plus_base + zone_size * i - zone_size * 0.1
        zone_up = plus_base + zone_size * (i + 1) + zone_size * 0.1
        # draw zone from zone_down to zone_up
        color = "green" if find_orders(zone_down, zone_up) else "red"
        ax.axhspan(zone_down, zone_up, color=color, alpha=0.2)
    minus_base = price - zone_size / 2
    for i in range(5):
        zone_down = minus_base - zone_size * (i + 1) - zone_size * 0.1
        zone_up = minus_base - zone_size * i + zone_size * 0.1
        # draw zone from zone_down to zone_up
        color = "green" if find_orders(zone_down, zone_up) else "red"
        ax.axhspan(zone_down, zone_up, color=color, alpha=0.2)


def get_zone(price: float, price_step, i):
    free_coef = 0.1
    zone_size = price * price_step
    if i > 0:
        zone_down = price + zone_size * (i - 1) - zone_size * free_coef + zone_size / 2
        zone_up = price + zone_size * i + zone_size * free_coef + zone_size / 2
    elif i < 0:
        i = -i
        zone_down = price - zone_size * i - zone_size * free_coef - zone_size / 2
        zone_up = price - zone_size * (i - 1) + zone_size * free_coef - zone_size / 2
    else:
        return price, price
    return zone_down, zone_up


def fill_orders(price):
    global limit_orders
    zone_size = price * price_step

    plus_base = price + zone_size / 2
    for i in range(5):
        zone_down = plus_base + zone_size * i - zone_size * 0.4
        zone_up = plus_base + zone_size * (i + 1) + zone_size * 0.4
        if not find_orders(zone_down, zone_up):
            limit_orders.append((zone_down + zone_up) / 2)

    minus_base = price - zone_size / 2
    for i in range(5):
        zone_down = minus_base - zone_size * (i + 1) - zone_size * 0.4
        zone_up = minus_base - zone_size * i + zone_size * 0.4
        if not find_orders(zone_down, zone_up):
            limit_orders.append((zone_down + zone_up) / 2)


ax = plt.gca()
fill_orders(base_price)
ax.axhline(y=base_price, color="g", linestyle="--")

# add slider for price
axcolor = "lightgoldenrodyellow"
ax_price = plt.axes([0.1, 0.1, 0.65, 0.03], facecolor=axcolor)
s_price = plt.Slider(ax_price, "Price", -10, 10, valinit=base_price)


# redraw zones
def update(val):
    ax.clear()
    for order in limit_orders:
        ax.axhline(y=order, color="r", linestyle="--")
    new_price = base_price * (1 + s_price.val / 100)
    ax.axhline(y=new_price, color="g", linestyle="--")
    for i in range(-5, 5):
        zone_down, zone_up = get_zone(new_price, price_step, i)
        color = "green" if find_orders(zone_down, zone_up) else "red"
        ax.axhspan(zone_down, zone_up, color=color, alpha=0.2)
    print(limit_orders)
    plt.draw()


s_price.on_changed(update)

# plt.show()


async def main():
    await tick()


if __name__ == "__main__":
    asyncio.run(main())
