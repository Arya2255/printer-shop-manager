import asyncio
import flet as ft

from shop.repository import Repository
from shop.ui import ShopApp


def main(page: ft.Page):
    repo = Repository("data/shop.db")
    app = ShopApp(page, repo, auto_sync=False)
    page.run_task(app.start)
