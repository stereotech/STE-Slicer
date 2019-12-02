# Copyright (c) 2017 Ultimaker B.V.
# Uranium is released under the terms of the LGPLv3 or higher.

from PyQt5.QtCore import Qt, QCoreApplication, QTimer
from PyQt5.QtGui import QPixmap, QColor, QFont, QPen, QPainter
from PyQt5.QtWidgets import QSplashScreen

from UM.Resources import Resources
from UM.Application import Application


class CuraSplashScreen(QSplashScreen):
    def __init__(self):
        super().__init__()
        self._scale = 0.7

        splash_image = QPixmap(Resources.getPath(Resources.Images, "cura.png"))
        self.setPixmap(splash_image)

        self._current_message = ""

        self._loading_image_rotation_angle = 0

        self._to_stop = False
        self._change_timer = QTimer()
        self._change_timer.setInterval(50)
        self._change_timer.setSingleShot(False)
        self._change_timer.timeout.connect(self.updateLoadingImage)

    def show(self):
        super().show()
        self._change_timer.start()

    def updateLoadingImage(self):
        if self._to_stop:
            return

        self._loading_image_rotation_angle -= 10
        self.repaint()

    # Override the mousePressEvent so the splashscreen doesn't disappear when clicked
    def mousePressEvent(self, mouse_event):
        pass

    def drawContents(self, painter):
        if self._to_stop:
            return

        painter.save()
        painter.setPen(QColor(255, 255, 255, 255))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.Antialiasing, True)

        version = Application.getInstance().getVersion().split("-")
        buildtype = Application.getInstance().getBuildType()
        if buildtype:
            version[0] += " (%s)" % buildtype

        # draw version text
        font = QFont()  # Using system-default font here
        font.setPixelSize(37)
        painter.setFont(font)
        painter.drawText(215, 66, 330 * self._scale, 230 * self._scale, Qt.AlignLeft | Qt.AlignTop, version[0])
        if len(version) > 1:
            font.setPixelSize(16)
            painter.setFont(font)
            painter.setPen(QColor(200, 200, 200, 255))
            painter.drawText(247, 105, 330 * self._scale, 255 * self._scale, Qt.AlignLeft | Qt.AlignTop, version[1])
        painter.setPen(QColor(255, 255, 255, 255))

        # draw the loading image
        pen = QPen()
        pen.setWidth(6 * self._scale)
        pen.setColor(QColor(32, 166, 219, 255))
        painter.setPen(pen)
        painter.drawArc(60, 150, 32 * self._scale, 32 * self._scale, self._loading_image_rotation_angle * 16, 300 * 16)

        # draw message text
        if self._current_message:
            font = QFont()  # Using system-default font here
            font.setPixelSize(13)
            pen = QPen()
            pen.setColor(QColor(255, 255, 255, 255))
            painter.setPen(pen)
            painter.setFont(font)
            painter.drawText(100, 128, 170, 64,
                             Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                             self._current_message)

        painter.restore()
        super().drawContents(painter)

    def showMessage(self, message, *args, **kwargs):
        if self._to_stop:
            return

        self._current_message = message
        self.messageChanged.emit(message)
        QCoreApplication.flush()
        self.repaint()

    def close(self):
        # set stop flags
        self._to_stop = True
        self._change_timer.stop()
        super().close()
