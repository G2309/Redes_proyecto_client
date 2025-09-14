import os
import asyncio
import logging
from pathlib import Path
from rich.panel import Panel
# Textual TUI
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Input, Static, Button
import claude_bot
import mcp_manager
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ASCII_ART placeholder 
ASCII_ART = r"""
                                                                ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣀⣀⣀⢀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⡀⣀⣀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣀⡀
                                                                ⠠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⣦⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣅⠩⠖⠤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⠄⠆
                                                                ⠠⠈⠀⠌⠀⠄⠠⠈⠠⠀⠄⠠⠁⠠⠀⠄⠠⠀⢄⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣎⠠⠄⠠⠈⠀⠄⠠⠁⠠⠀⠄⠁⠄⠠⠀⠄⠨⠅
                                                                ⠠⠁⠈⠀⠈⠀⠁⠀⠁⠠⠈⠀⠈⠀⠄⠀⠡⣪⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣍⢅⠈⠀⠈⠀⠈⠀⠁⠠⠈⠀⠄⠁⠠⠠⠅
                                                                ⢀⡀⣀⢀⡀⣀⢀⡀⣀⠀⣀⠀⡀⢀⡀⢄⣵⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣆⢢⡀⡀⢀⡀⣀⠀⣀⠀⣀⠀⡀⢀⢀⡆
                                                                ⢀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⢀⠀⢔⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠑⡀⠀⠀⠀⡀⠀⢀⠀⢀⠀⠀⢂⡂
                                                                ⠀⠂⠐⠐⠀⠒⠀⠒⠀⠐⠀⠂⢀⢎⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠐⡀⠂⠐⠀⠂⠀⠂⠀⠂⠐⠀⡆
                                                                ⠰⠠⠠⠄⠤⠀⠤⠀⠤⠀⠄⠄⢂⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⢢⠀⠄⠤⠠⠄⠤⠠⠀⠄⠢⠅
                                                                ⠠⠀⠄⠠⠀⠄⠀⠄⠀⠠⠀⠰⣹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣿⡛⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠆⠀⠀⠄⠠⠀⠠⠀⠠⠠⠅
                                                                ⠈⠀⠈⠀⠀⠈⠀⠈⠀⠁⢨⢡⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠁⠀⠀⠈⣿⡟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⠈⠀⠁⠀⠀⠁⠀⠁⠀⠁⠇
                                                                ⠐⡀⢀⠀⡀⢀⠀⡀⠀⢀⠂⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⠀⠀⠀⠀⢹⡇⢿⣿⣿⣿⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠁⠀⠀⡀⢀⠀⡀⠀⡀⡆
                                                                ⠐⠀⠂⠀⠐⠀⡀⠐⠀⠒⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⢸⠀⢸⣿⣿⣿⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠃⠐⠀⠐⠀⡀⠐⠀⠒⡂
                                                                ⠀⠐⠀⠐⠀⠀⠀⠀⠀⢲⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀⠀⠀⠀⢈⠀⢸⣿⣿⡟⠀⡿⠋⡿⢹⠿⣿⣿⣿⣿⠃⢿⠟⣿⡟⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣏⢰⠀⠀⠀⠀⠀⠀⠀⠐⠂
                                                                ⠰⠠⠄⠤⠠⠄⠤⠠⠄⠃⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠙⡄⠀⣀⠀⠀⠠⠀⠘⠁⠙⠃⠀⠁⠀⠀⠀⣠⣤⣶⠶⠿⠶⠼⢤⣼⣁⣹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠈⠀⠄⠄⠢⠄⠤⠀⠌⠇
                                                                ⢀⠀⠀⠀⠀⠀⠀⠀⠀⠃⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠸⣿⣿⣿⣻⣇⡼⠼⠿⠿⠛⠛⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠸⠃⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠘⡃
                                                                ⠀⠂⠐⠀⠂⠐⠀⠂⠐⠀⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡠⢽⡿⠻⠃⠀⠀⢀⠀⠀⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠊⠀⢀⣠⣤⣤⣀⣀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠐⠀⠂⠐⠀⠂⠐⠆
                                                                ⠠⠄⠄⠠⠀⠄⠠⠀⠄⠹⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⢀⣠⣤⣦⡤⠤⢄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠟⠉⣾⣿⣿⣿⣛⡙⠲⣀⠀⠘⠛⣿⣿⣿⣿⣿⣿⣿⣿⡧⢠⠀⠄⠠⠀⠄⠠⠀⠌⠇
                                                                ⠠⠈⠀⠄⠁⠠⠀⠄⠠⠁⠈⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⣠⠴⣻⣿⣿⣿⣽⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠛⠿⠿⠿⠿⠧⠄⠁⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⡇⠘⠀⠀⠄⠁⠀⠁⠀⠌⠅
                                                                ⠀⠀⠁⠀⠈⠀⠀⠀⠀⠈⠀⢿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠇⠘⠡⠀⢿⡿⠿⠛⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣧⡙⢿⣿⣿⣿⣿⣿⠁⠆⠀⠁⠈⠀⠁⠈⠀⠈⡅
                                                                ⢐⠀⡀⢀⠀⡀⢀⠀⡀⢀⠃⠸⣿⣿⣿⣿⣿⣿⣿⣿⠃⠀⠀⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣤⠙⣋⣴⣿⡿⠐⡂⢀⠀⡀⢀⠀⡀⢀⠀⡆
                                                                ⢀⠂⠐⠀⠂⠐⠀⠂⠀⠒⠘⡀⢿⣿⣿⣿⢿⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣿⡿⢋⣴⡙⣿⣿⠇⠠⠐⠀⠂⠐⠀⠂⠐⠀⠒⡂
                                                                ⠠⠀⠄⠠⠀⠄⠠⠀⠄⠠⠀⢣⠸⣿⣿⣿⣧⣿⣿⣿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣫⣶⣿⣿⣿⣾⡏⢀⠆⠀⠠⠀⠄⠠⠀⠄⠀⠄⠆
                                                                ⠠⠄⠤⠀⠤⠀⠄⠄⠠⠀⠌⠤⠆⢻⣿⣿⣿⡿⣿⣯⣷⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⠀⠌⠠⠄⠤⠀⠤⠀⠤⠀⠄⠌⠇
                                                                ⠈⠀⠀⠀⠀⠀⠈⠀⠀⠀⠈⠀⠄⠘⣿⣿⣿⣿⣿⣧⡿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣾⣿⣿⣿⣿⣿⣿⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠅
                                                                ⠘⠀⠁⠈⠀⠁⠈⠀⠁⠈⠀⢈⠘⡀⢻⣿⣿⣿⣿⣿⣯⣼⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠐⠒⠒⠀⠀⠈⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⣿⣿⣿⣿⣿⣿⣿⢰⠀⠈⠀⠁⠈⠀⠁⠈⠀⠁⡈⡃
                                                                ⠐⢂⠂⠂⠒⠀⢂⠂⠐⠂⡐⠀⠂⣃⠸⡇⠹⣿⣿⣿⣿⣿⣿⣿⣿⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣾⣿⣿⣿⣿⣿⣿⡿⠃⢀⠀⢂⠐⡀⠒⠀⠒⢀⠂⠐⠐⡂
                                                                ⠐⠀⠀⠐⠀⠀⠀⠀⠂⠀⠀⠀⠒⠘⢠⠒⢆⠸⣿⣿⣿⣿⣿⣿⣿⣿⣝⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⠀⠔⢂⠒⠀⠀⠀⠀⠂⠀⠀⠀⠐⠐⡂
                                                                ⠠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠈⡀⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⡧⢰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⠅
                                                                ⠠⠌⠠⠁⠌⠠⠁⠌⠠⠁⠌⠠⠁⠄⠈⠠⠁⠅⢺⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣤⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠄⠠⠀⠌⠠⠁⠌⠠⠁⠌⠠⠁⠄⠁⠇
                                                                ⠀⠈⠀⠈⠀⠀⠁⠀⠁⠀⠈⠀⠈⠀⠁⠀⠁⠀⠸⠈⣿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⡀⠀⠀⠀⢀⣠⣤⣾⣿⡗⠈⢻⣿⣿⣿⣿⣿⡿⣿⣿⣿⣿⣿⣿⠀⠉⠀⠁⠈⠀⠈⠀⠁⠈⠀⠀⠁⠈⠈⠅
                                                                ⠘⠐⠀⠂⠐⠀⠂⠐⠀⠂⠐⠀⠂⠐⠀⠂⠐⢒⡓⡆⢛⠈⠻⠈⢿⠟⢿⣿⣿⢿⣿⣿⡿⣿⣿⠿⣹⢿⣿⣿⣿⣿⣿⣿⣿⠟⠟⠀⠀⡾⠋⠈⠻⠋⠈⠀⣈⢹⣿⣿⣿⡇⢀⠃⠐⠀⠂⠐⠀⠂⠐⠀⠂⠐⠀⠂⡐⡃
                                                                ⠐⢂⠐⢀⠂⡐⢀⠂⡐⢀⠂⡐⢀⠂⡐⠀⢂⠀⠐⠒⣐⣒⣀⣣⣀⣂⡀⠉⠛⡈⠉⢿⠇⠀⠀⠀⠉⠙⠻⠿⠿⠟⠛⠉⠀⠀⠀⠀⠀⠂⣔⣚⣂⢄⣛⠚⠐⣿⣿⣿⣿⠀⡈⠐⢀⠂⡐⠀⢂⠐⡀⠂⡐⠀⢂⠐⢀⡃
                                                                ⢀⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⠀⠀⠀⢀⠐⠐⣊⣂⣖⣳⠴⣸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⢒⡀⠀⡀⠀⠀⣐⣿⣿⣿⡇⢠⠁⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⡀⢀⠀⡀⡆
                                                                ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠁⠈⠀⠀⠀⠀⠀⠈⠀⢠⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢫⠄⠀⠀⠀⠁⢨⣿⣿⣿⠀⡌⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⠅
                                                                ⠈⠁⠌⠠⠁⠌⠠⠁⠌⠠⠁⠈⠀⠁⠈⠄⠡⢈⣤⠥⠬⢤⠡⠄⠥⠬⠄⠡⠘⠋⠙⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠫⢍⠤⠅⠨⣽⣿⣿⡏⠰⠀⠠⠁⠌⠠⠁⠌⠠⠁⠌⠠⠁⠌⠀⠡⠠⠅
                                                                ⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣤⠌⠒⠉⠁⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠑⠪⢁⣽⣿⣿⠁⠂⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡅
                                                                ⠐⢀⠂⠐⠀⠂⠐⠀⡀⢂⣐⢾⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠗⠠⢍⡒⣀⢂⠀⠐⠀⠂⠐⠀⠂⠐⠀⠂⠐⠀⡐⡂
                                                                ⢐⠀⡐⠀⢂⠐⠀⠂⣐⠖⠀⠀⠙⣏⡇⠀⠀⠀⠀⠀⠀⠀⠁⠀⢀⡀⠀⠠⠤⠄⠀⠐⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠤⠀⣀⡀⠀⠀⠀⠀⢠⣿⡟⠀⠀⠀⠀⠁⣶⣒⡒⠒⡀⠂⠐⡀⢂⠐⡀⠂⠐⣀⡃
                                                                ⢀⠀⠀⠀⠀⠀⠀⡴⠁⠀⠀⠀⠀⣽⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⢸⣿⠃⠀⠀⠀⠀⠀⣳⠿⠿⣷⣤⡂⣀⠀⠀⠀⠀⠀⠀⠀⡆
                                                                ⠈⠁⠁⠈⠀⠡⡹⠁⠀⠀⠀⠀⠀⣯⡇⠀⠀⠀⠀⠀⠀⠀⠘⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣾⠃⠀⠀⠀⠀⠀⠀⢸⢰⠀⠈⠙⠻⠮⡭⠅⠈⠁⠈⠀⠉⠅
                                                                ⠨⠀⠄⠁⠄⡰⠁⠀⠀⠀⠀⠀⠀⣎⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠑⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⠏⠀⠀⠀⠀⠀⠀⠀⢸⣼⡀⠀⠀⠀⠀⠈⢯⠡⠄⠠⠁⠈⡅
                                                                ⣸⠤⠀⡀⣀⠃⠀⠀⠀⠀⠀⠀⢀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠑⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡠⠀⠀⠎⠀⠀⠀⠀⠀⠀⠀⠀⢸⡷⡄⠀⠀⠀⠀⠀⠀⠱⡀⠀⡀⢈⡆
                                                                ⣼⣿⣷⣶⣿⣷⣶⣶⣶⣶⣶⣶⣾⣿⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣿⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣿⣶⣶⣾⣶⣶⣶⣶⣶⣶⣶⣶⣶⣾⣿⣷⣶⣶⣶⣶⣶⣶⣾⣷⣾⣶⣷⡖
                                                                ⢼⣿⡟⠛⢻⣿⣿⣿⣿⣿⣿⡟⠛⠛⠛⠛⠛⠛⠛⢻⡟⠛⠛⠛⠛⠛⠛⠛⠛⣿⡿⠛⠛⠛⠛⠛⠛⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠛⠛⠛⠛⠛⠛⣿⡟⠛⢻⣿⣿⣿⣿⣿⣿⣿⡿⠛⠛⣿⣿⣿⣿⣿⣿⣿⣿⡗
                                                                ⢺⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⡇⠀⢀⣠⣀⣀⣀⣀⣸⣇⣀⣀⡀⠀⢀⣀⣀⣀⣿⠀⠀⣄⣀⣀⣀⡀⠀⢸⣿⣿⣿⣿⣿⣿⣿⠟⠁⠀⢀⣀⣀⡀⠀⠀⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⣿⡟⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣏
                                                                ⣹⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⡇⠀⠘⠿⠿⠻⠿⠿⣿⣿⣿⣿⡇⠀⢸⣿⣿⣿⣿⠀⠀⠿⠻⠿⠻⠿⠾⣿⣿⣿⣿⣿⣿⣿⠅⠀⢀⣾⣿⣿⣿⡇⠀⠀⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⣿⣏⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⡧
                                                                ⢼⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⡇⠀⢀⣀⣀⣀⣀⣀⣿⣿⣿⣿⡇⠀⢸⣿⣿⣿⣿⣄⣀⣀⣀⣀⣀⡀⠀⢸⣿⣿⣿⣿⣿⣿⠂⠀⠈⠉⠉⠉⠉⠁⠀⠀⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⣿⣏⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⡗
                                                                ⢺⣿⡇⠀⠸⠿⠿⠿⠿⠿⣿⡇⠀⠸⠿⠿⠿⠿⠿⢿⣿⣿⣿⡇⠀⢸⣿⣿⣿⣿⠉⠉⠿⠿⠿⠿⠇⠀⢸⣿⣿⣿⣿⣿⣿⡁⠀⢰⣶⣶⣶⣶⡆⠀⠀⣿⡇⠀⠸⠿⠿⠿⠿⠿⠿⢿⣧⠀⠀⠿⠿⠿⠿⠿⠿⢿⣿⣏
                                                                ⣹⣿⡇⡀⢀⢀⡀⢀⡀⢀⣼⡇⣀⠀⣀⠀⣀⠀⡀⣸⣿⣿⣿⣇⠀⣸⣿⣿⣿⣿⣄⡀⢀⡀⢀⡀⢀⣀⣼⣿⣿⣿⣿⣿⣿⡄⣀⣸⣿⣿⣿⣿⣇⢀⢀⣿⡇⣀⠀⣀⠀⣀⢀⡀⢀⣸⣷⢀⢀⠀⣀⢀⡀⡀⢀⢸⣿⡧
                                                                ⢼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡗
                                                                ⢺⣿⡇⢄⢻⣿⣿⣿⣿⣿⣿⡟⢠⠐⡄⢢⠐⡄⣈⢻⣿⡐⢸⣿⣿⣿⣿⡇⠄⣿⣟⠠⡐⢄⠢⡐⢄⡂⣽⣿⣿⣿⣿⣿⣿⡇⠀⢸⣿⣿⣿⣿⣿⣿⣿⡟⠁⠀⠀⠀⠀⠀⢸⣿⠀⠀⣿⡇⠀⠈⢻⣿⣿⣟⠀⢸⣿⣏
                                                                ⣹⣿⡇⠌⣾⣿⣿⣿⣿⣿⣿⣇⠂⣿⣿⣿⣿⣿⢀⢻⣿⠌⢲⣿⣿⣿⣿⡇⢊⣿⣯⠐⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⢸⣿⣿⣿⣿⣿⣿⠏⠀⢀⣼⣿⣿⡇⠀⢸⣿⠀⠀⣿⡇⠀⠀⠀⠻⣿⣯⠀⢸⣿⡧
                                                                ⢼⣿⡇⢊⣼⣿⣿⣿⣿⣿⣿⡇⠌⣿⣿⣿⣿⣿⢀⢻⣿⡘⢰⣿⣿⣿⣿⡇⢂⣿⡷⢈⠄⢂⠔⡠⠌⢸⣿⣿⣿⣿⣿⣿⣿⡆⠀⢸⣿⣿⣿⣿⣿⣿⠂⠀⠛⠛⠻⠛⠃⠀⢸⣿⠀⠀⣿⡇⠀⢸⡄⠀⠙⡷⠀⢸⣿⡗
                                                                ⢺⣿⡇⠡⣾⣿⣿⣿⣿⣿⣿⡏⡐⣿⣿⣿⣿⣿⢀⢻⣿⡡⠌⠻⣿⣿⠟⡉⢄⣿⡿⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⢸⣿⣿⣿⣿⣿⣿⡁⠀⣀⣀⣀⣀⡀⠀⢸⣿⠀⠀⣿⡇⠀⢸⣿⣆⠀⠈⠀⢸⣿⣏
                                                                ⣹⣿⡇⠱⡈⢉⡉⡉⣉⠉⣿⣇⠰⢉⢉⡉⢉⠔⠂⣽⣿⣿⣦⡡⠌⡑⣈⣴⣿⣿⣟⠡⣈⠡⡉⢌⢉⡉⣽⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⣿⡁⠀⣿⣿⣿⣿⡇⠀⢸⣿⠀⠀⣿⡇⠀⢸⣿⣿⣧⡀⠀⢸⣿⡧
                                                                ⢼⣿⣿⣶⣷⣷⣶⣷⣶⣾⣿⣿⣷⣾⣶⣾⣶⣾⣿⣿⣿⣿⣿⣷⣾⣶⣾⣿⣿⣿⣿⣶⣶⣷⣾⣶⣶⣶⣿⣿⣿⣿⣿⣿⣿⣷⣶⣶⣶⣶⣶⣶⣶⣿⣷⣶⣿⣿⣿⣿⣷⣶⣾⣿⣶⣶⣿⣷⣶⣾⣿⣿⣿⣷⣶⣾⣿⡗
                                                                ⠘⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉⠋⠙⠉
"""

# Catppuccin colors from: https://catppuccin.com/palette/  
# catppuccin macchiato
MAUVE = "#c6a0f6"
YELLOW = "#eed49f"
SKY = "#91d7e3"
BLUE = "#8aadf4"
MANTLE = "#1e2030"
BASE = "#24273a"
TEXT = "#cad3f5"
RED = "#ed8796"


class ChatApp(App):
    # App CSS using your Catppuccin palette
    CSS = f"""
    Screen {{
        background: {MANTLE};
        color: {TEXT};
        layout: vertical;
        padding: 0;
    }}

    Header, Footer {{
        background: {BASE};
        color: {TEXT};
        height: auto;
    }}

    #main {{
        height: 1fr;
    }}

    #messages {{
        border: round {MAUVE};
        background: {BASE};
        color: {TEXT};
        height: 1fr;
        padding: 1 1;
        overflow: auto;
    }}

    #messages_content {{
        background: transparent;
        color: {TEXT};
        padding: 1 1;
    }}

    #sidebar {{
        border: round {BLUE};
        background: {MANTLE};
        color: {TEXT};
        width: 36;
        padding: 1 1;
        height: 1fr;
    }}

    #sidebar_content {{
        background: transparent;
        color: {TEXT};
        padding: 0 0;
    }}

    Input {{
        height: 3;
        border: round {MAUVE};
        background: {BASE};
        color: {TEXT};
    }}

    Static {{
        color: {TEXT};
    }}

    Button {{
        border: round {SKY};
        background: {BASE};
        color: {TEXT};
    }}

    /* small helper for error text */
    .error {{
        color: {RED};
        text-style: bold;
    }}
    """

    # Initialize application instance variables
    def __init__(self, api_key: str, mcp_servers: list, max_context: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.mcp_servers = mcp_servers
        self.max_context = max_context
        self._conversation_text = ""  # aggregated conversation text
        self._sending_task = None
        # flag to control assistant streaming label printing
        self._assistant_streaming = False

    # Compose the UI synchronously for Textual
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical():
                yield ScrollableContainer(
                    Static(ASCII_ART, id="messages_content"),
                    id="messages",
                )
                yield Input(
                    placeholder="Type a message and press Enter — commands: /help /quit /clear /tools /stats",
                    id="input",
                )
            # Sidebar ahora es un ScrollableContainer con Static interno
            yield ScrollableContainer(
                Static("Initializing tools...", id="sidebar_content"),
                id="sidebar",
            )
        yield Footer()
    
    # Initialize bot and UI elements
    async def on_mount(self) -> None:
        try:
            await claude_bot.initialize(
                api_key=self.api_key, mcp_servers=self.mcp_servers, max_context=self.max_context
            )
        except Exception as e:
            logger.exception("claude_bot.initialize() failed")
            try:
                sidebar = self.query_one("#sidebar", Static)
                sidebar.update(f"Error initializing tools: {e}")
            except Exception:
                pass

        try:
            await self._refresh_sidebar()
        except Exception:
            logger.exception("Error refreshing sidebar")

        # focus input widget (focus() is synchronous / not awaitable)
        try:
            input_widget = self.query_one("#input", Input)
            if input_widget is not None:
                input_widget.focus()
            else:
                logger.warning("Input widget not found to focus()")
        except Exception:
            logger.exception("Failed to focus the input widget")

        # remove the startup ASCII after n seconds
        try:
            # schedules callback which launches an async task
            self.set_timer(3.0, lambda: asyncio.create_task(self._remove_startup_art_async()))
        except Exception:
            # fallback if set_timer not present
            asyncio.create_task(self._remove_startup_art_fallback())


    # Update the sidebar with available MCP tools
    async def _refresh_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", ScrollableContainer)
        try:
            content = sidebar.query_one("#sidebar_content", Static)
        except Exception:
            # fallback: si no existe, crea/obtén el Static directamente
            content = self.query_one("#sidebar_content", Static)
    
        tools = mcp_manager.get_available_tools()
        lines = []
        if tools:
            for server_name, server_tools in tools.items():
                lines.append(f"[b]{server_name}[/b]")
                for t in server_tools:
                    desc = getattr(t, "description", "")
                    name = getattr(t, "name", getattr(t, "id", str(t)))
                    lines.append(f" • {name} - {desc}")
        else:
            lines.append("No MCP tools available")
        content.update("\n".join(lines))
    
        # intenta desplazar al final para que el usuario vea lo último
        try:
            await sidebar.scroll_end(animate=False)
        except Exception:
            # algunos backends/textual versions pueden no soportar scroll_end asíncrono
            logger.debug("sidebar.scroll_end no está disponible; ignorando")

    # Append a message to the conversation view, then scroll
    async def append_message(self, chunk: str, role: str = "assistant") -> None:
        if role == "user":
            # user message formatting
            self._conversation_text += f"\n[bold green]You:[/bold green] {chunk}\n"
            # if user sends a message, ensure assistant streaming flag reset
            self._assistant_streaming = False
        else:
            # assistant (LainBot) streaming handling:
            label = "\n[bold cyan]LainBot:[/bold cyan] "
            if not self._assistant_streaming:
                # first assistant chunk: prepend label
                self._conversation_text += f"{label}{chunk}"
                self._assistant_streaming = True
            else:
                # subsequent chunks during streaming: append directly
                self._conversation_text += chunk

        # update UI elements and scroll to end (scroll_end may be awaitable)
        messages_container = self.query_one("#messages", ScrollableContainer)
        inner = self.query_one("#messages_content", Static)
        inner.update(self._conversation_text)
        try:
            await messages_container.scroll_end(animate=False)
        except Exception:
            logger.debug("scroll_end failed or not awaitable; ignoring")

    # Send a message and stream assistant response
    async def handle_send(self, message: str) -> None:
        try:
            # show user message immediately
            await self.append_message(message, role="user")
            # stream assistant response
            async for chunk in claude_bot.send_message_stream(message):
                await self.append_message(chunk, role="assistant")
            # streaming finished: reset streaming flag and finalize formatting
            self._assistant_streaming = False
            # optionally save session
            try:
                await claude_bot.save_session()
            except Exception:
                pass
        except Exception as e:
            logger.exception("Error while sending message")
            await self.append_message(f"\n[red]Error: {e}[/red]\n")

    # Show help text to the user
    async def action_show_help(self) -> None:
        await self.append_message(
            "/help: show help. /quit: exit. /clear: clear history. /tools: show MCP tools. /stats: show stats\n",
            role="assistant",
        )

    # Refresh tools list and notify user
    async def action_show_tools(self) -> None:
        await self._refresh_sidebar()
        await self.append_message("(Updated MCP tools list on the right)\n", role="assistant")

    # Show conversation and context stats
    async def action_show_stats(self) -> None:
        stats = claude_bot.get_conversation_stats()
        text = (
            f"Total messages: {stats['total']}\n"
            f"User messages: {stats['user']}\n"
            f"Assistant messages: {stats['assistant']}\n"
            f"Context window: {stats['context_window']} messages\n"
        )
        await self.append_message(text, role="assistant")

    # Clear conversation history and UI
    async def action_clear(self) -> None:
        claude_bot.clear_history()
        try:
            await claude_bot.save_session()
        except Exception:
            pass
        self._conversation_text = ""
        inner = self.query_one("#messages_content", Static)
        inner.update(self._conversation_text)
        self._assistant_streaming = False

    # Handle input submitted events
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        # clear the input box
        event.input.value = ""
        if not text:
            return

        if text.startswith("/"):
            cmd = text.lower()
            if cmd == "/quit":
                await self.action_quit()
            elif cmd == "/help":
                await self.action_show_help()
            elif cmd == "/clear":
                await self.action_clear()
            elif cmd == "/tools":
                await self.action_show_tools()
            elif cmd == "/stats":
                await self.action_show_stats()
            else:
                await self.append_message(f"Unknown command: {text}\n", role="assistant")
            return

        # start send task 
        asyncio.create_task(self.handle_send(text))

    # Cleanup resources on shutdown
    async def on_shutdown_request(self) -> None:
        try:
            await claude_bot.cleanup()
        except Exception:
            pass

    # Remove startup ASCII art and show conversation
    async def _remove_startup_art_async(self) -> None:
        try:
            inner = self.query_one("#messages_content", Static)
            inner.update(self._conversation_text)
            try:
                messages_container = self.query_one("#messages", ScrollableContainer)
                await messages_container.scroll_end(animate=False)
            except Exception:
                logger.debug("scroll_end failed or not awaitable; ignoring")
        except Exception:
            logger.exception("Failed to remove startup ASCII art")

    # Fallback removal if timers are unavailable
    async def _remove_startup_art_fallback(self) -> None:
        await asyncio.sleep(3.0)
        await self._remove_startup_art_async()


# Parse env, build config, and start app
def main():
    api_key = os.getenv("Anthropic_API_key")
    if not api_key:
        print("Please set an anthropic api key")
        raise SystemExit(1)

    # load MCP config if present
    config_file = os.getenv("MCP_CONFIG", "mcp_config.json")
    mcp_servers = []
    if Path(config_file).exists():
        import json

        with open(config_file, "r") as f:
            cfg = json.load(f)
        for s in cfg.get("servers", []):
            mcp_servers.append(
                mcp_manager.MCPServerConfig(
                    name=s.get("name"),
                    command=s.get("command"),
                    args=s.get("args"),
                    env=s.get("env"),
                    url=s.get("url"),
                    transport=s.get("transport", "stdio"),
                    description=s.get("description", ""),
                )
            )

    app = ChatApp(
        api_key=api_key, mcp_servers=mcp_servers, max_context=int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    )
    app.run()


if __name__ == "__main__":
    main()

