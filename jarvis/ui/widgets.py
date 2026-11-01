"""Petits composants partagés par la fenêtre de discussion et les Paramètres."""
from PySide6.QtWidgets import QLabel


class WrapLabel(QLabel):
    """QLabel à retour à la ligne qui réclame toujours la hauteur de son texte.

    Sans cela, Qt calcule parfois la hauteur pour une autre largeur et coupe la fin du texte
    (ex. une conversation rouverte, dessinée avant que la fenêtre ait sa taille).
    """

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)

    def setText(self, text: str) -> None:
        super().setText(text)
        h = self.heightForWidth(self.width())
        if h > 0:
            self.setMinimumHeight(h)
