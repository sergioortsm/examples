

import webbrowser


class Utils:
    @staticmethod
    def comparar_por_title(item):
        return item["Title"].lower()
        
    @staticmethod
    def open_list_url(url: str, e):
        webbrowser.open(url, new=2)  # new=2 → nueva pestaña