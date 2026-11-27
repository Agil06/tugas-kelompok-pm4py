"""Interactive PySide6 QGraphicsView vector renderer for Process Maps, Petri Nets, and Process Trees."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from bpic17_app.discovery import DiscoveryResult, GraphEdge, GraphNode


def _heat_color(heat: float) -> QColor:
    """Interpolate heat (0..1) from slate-blue to amber to red."""
    h = max(0.0, min(1.0, float(heat)))
    if h < 0.5:
        t = h / 0.5
        r = int(56 + (245 - 56) * t)
        g = int(189 + (158 - 189) * t)
        b = int(248 + (11 - 248) * t)
    else:
        t = (h - 0.5) / 0.5
        r = int(245 + (239 - 245) * t)
        g = int(158 + (68 - 158) * t)
        b = int(11 + (68 - 11) * t)
    return QColor(r, g, b)


class DraggableNodeItem(QGraphicsItem):
    """Interactive vector node supporting drag, selection, and dynamic edge updates."""

    def __init__(self, node: GraphNode, on_select=None) -> None:
        super().__init__()
        self.node = node
        self._on_select = on_select
        self.edges: List["CurvedEdgeItem"] = []

        self.setPos(node.x, node.y)
        self.setZValue(2.0)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setToolTip(node.detail or node.label)

        if node.kind in ("start", "end", "place"):
            self._w, self._h = 44.0, 44.0
        elif node.kind == "tau":
            self._w, self._h = 34.0, 34.0
        elif node.kind == "operator":
            self._w, self._h = 56.0, 38.0
        else:
            est_w = max(130.0, min(220.0, len(node.label) * 7.6 + 26.0))
            self._w, self._h = est_w, 50.0 if node.subtitle else 40.0

    def boundingRect(self) -> QRectF:
        return QRectF(-self._w / 2.0 - 4, -self._h / 2.0 - 4, self._w + 8, self._h + 8)

    def half_size(self) -> Tuple[float, float]:
        return self._w / 2.0, self._h / 2.0

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        rect = QRectF(-self._w / 2.0, -self._h / 2.0, self._w, self._h)
        selected = self.isSelected()
        kind = self.node.kind

        if kind in ("start", "end", "place"):
            fill = (
                QColor("#065f46")
                if kind == "start"
                else (QColor("#7f1d1d") if kind == "end" else QColor("#1e293b"))
            )
            border = (
                QColor("#38bdf8")
                if selected
                else (
                    QColor("#34d399")
                    if kind == "start"
                    else (QColor("#f87171") if kind == "end" else QColor("#94a3b8"))
                )
            )
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(border, 2.5 if selected else 1.8))
            painter.drawEllipse(rect)
            if self.node.label:
                painter.setPen(QColor("#f8fafc"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.drawText(rect, Qt.AlignCenter, self.node.label)
            elif kind == "place":
                # Small dot center for clarity
                painter.setBrush(QBrush(QColor("#475569")))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(0, 0), 3.0, 3.0)
            return

        if kind == "tau":
            painter.setBrush(QBrush(QColor("#020617")))
            painter.setPen(QPen(QColor("#38bdf8") if selected else QColor("#64748b"), 2.0))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor("#cbd5e1"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, "τ")
            return

        if kind == "operator":
            painter.setBrush(QBrush(QColor("#312e81")))
            painter.setPen(QPen(QColor("#38bdf8") if selected else QColor("#818cf8"), 2.0))
            painter.drawRoundedRect(rect, 10, 10)
            painter.setPen(QColor("#f8fafc"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, self.node.label)
            return

        # Activity / Transition card
        base_color = QColor("#1e293b")
        if self.node.heat > 0.65:
            base_color = QColor("#2a1e2e")
        border_col = QColor("#38bdf8") if selected else _heat_color(self.node.heat)
        painter.setBrush(QBrush(base_color))
        painter.setPen(QPen(border_col, 2.5 if selected else 1.6))
        painter.drawRoundedRect(rect, 8, 8)

        painter.setPen(QColor("#f8fafc"))
        painter.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        if self.node.subtitle:
            top_r = QRectF(rect.left() + 6, rect.top() + 4, rect.width() - 12, 22)
            bot_r = QRectF(rect.left() + 6, rect.top() + 26, rect.width() - 12, 18)
            painter.drawText(top_r, Qt.AlignCenter | Qt.TextSingleLine, self.node.label)
            painter.setPen(QColor("#38bdf8"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(bot_r, Qt.AlignCenter | Qt.TextSingleLine, self.node.subtitle)
        else:
            painter.drawText(
                rect.adjusted(6, 2, -6, -2),
                Qt.AlignCenter | Qt.TextWordWrap,
                self.node.label,
            )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in self.edges:
                e.update_geometry()
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            is_sel = bool(value)
            for e in self.edges:
                e.set_highlighted(is_sel)
            if is_sel and self._on_select:
                self._on_select(self.node.detail or self.node.label)
        return super().itemChange(change, value)


class CurvedEdgeItem(QGraphicsPathItem):
    """Curved cubic Bezier edge with arrowhead, midpoint label, and hover/highlight styling."""

    def __init__(
        self,
        edge: GraphEdge,
        src_item: DraggableNodeItem,
        tgt_item: DraggableNodeItem,
        curve_offset: float = 0.0,
        on_select=None,
    ) -> None:
        super().__init__()
        self.edge = edge
        self.src_item = src_item
        self.tgt_item = tgt_item
        self.curve_offset = curve_offset
        self._on_select = on_select
        self._highlighted = False
        self._arrow_poly = QPolygonF()
        self._label_pos = QPointF()

        self.setZValue(1.0)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setToolTip(edge.detail or edge.label)

        src_item.edges.append(self)
        if tgt_item is not src_item:
            tgt_item.edges.append(self)

        self.update_geometry()

    def set_highlighted(self, highlighted: bool) -> None:
        self._highlighted = highlighted
        self.setZValue(3.0 if highlighted else 1.0)
        self.update()

    @staticmethod
    def _clip_to_box(center: QPointF, target: QPointF, hw: float, hh: float) -> QPointF:
        dx = target.x() - center.x()
        dy = target.y() - center.y()
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return center
        sx = hw / abs(dx) if abs(dx) > 1e-6 else 1e9
        sy = hh / abs(dy) if abs(dy) > 1e-6 else 1e9
        t = min(sx, sy)
        return QPointF(center.x() + dx * t, center.y() + dy * t)

    def update_geometry(self) -> None:
        self.prepareGeometryChange()
        p1_c = self.src_item.pos()
        p2_c = self.tgt_item.pos()
        hw1, hh1 = self.src_item.half_size()
        hw2, hh2 = self.tgt_item.half_size()

        path = QPainterPath()
        if self.src_item is self.tgt_item:
            # Self-loop arc above node
            start = QPointF(p1_c.x() - hw1 * 0.35, p1_c.y() - hh1)
            end = QPointF(p1_c.x() + hw1 * 0.35, p1_c.y() - hh1)
            c1 = QPointF(p1_c.x() - hw1 * 0.8, p1_c.y() - hh1 - 56.0)
            c2 = QPointF(p1_c.x() + hw1 * 0.8, p1_c.y() - hh1 - 56.0)
            path.moveTo(start)
            path.cubicTo(c1, c2, end)
            self._label_pos = QPointF(p1_c.x(), p1_c.y() - hh1 - 42.0)
            tangent = end - c2
            tip = end
        else:
            dx = p2_c.x() - p1_c.x()
            dy = p2_c.y() - p1_c.y()
            dist = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / dist, dx / dist

            mid = QPointF((p1_c.x() + p2_c.x()) / 2.0, (p1_c.y() + p2_c.y()) / 2.0)
            # Subtle natural curve + explicit separation for bidirectional or back-edges
            offset = self.curve_offset
            if dx < -20.0 and abs(offset) < 1e-3:
                offset = -45.0

            ctrl = QPointF(mid.x() + nx * offset, mid.y() + ny * offset)
            start = self._clip_to_box(p1_c, ctrl, hw1 + 2.0, hh1 + 2.0)
            end = self._clip_to_box(p2_c, ctrl, hw2 + 4.0, hh2 + 4.0)

            path.moveTo(start)
            path.quadTo(ctrl, end)
            self._label_pos = path.pointAtPercent(0.5)
            tangent = end - ctrl
            tip = end

        self.setPath(path)

        # Compute arrowhead polygon
        ang = math.atan2(tangent.y(), tangent.x())
        arrow_len = 9.0
        arrow_ang = math.radians(26.0)
        p_left = QPointF(
            tip.x() - arrow_len * math.cos(ang - arrow_ang),
            tip.y() - arrow_len * math.sin(ang - arrow_ang),
        )
        p_right = QPointF(
            tip.x() - arrow_len * math.cos(ang + arrow_ang),
            tip.y() - arrow_len * math.sin(ang + arrow_ang),
        )
        self._arrow_poly = QPolygonF([tip, p_left, p_right])

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-60, -24, 60, 24)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        base_col = _heat_color(self.edge.heat)
        if self._highlighted or self.isSelected():
            col = QColor("#f8fafc")
            width = 3.2
        else:
            col = base_col
            width = 1.4 + self.edge.heat * 2.4

        painter.setPen(QPen(col, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

        painter.setBrush(QBrush(col))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(self._arrow_poly)

        if self.edge.label:
            font = QFont("Segoe UI", 8, QFont.DemiBold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self.edge.label) + 10
            th = fm.height() + 4
            pill = QRectF(
                self._label_pos.x() - tw / 2.0,
                self._label_pos.y() - th / 2.0,
                tw,
                th,
            )
            painter.setBrush(QBrush(QColor("#0f172a")))
            painter.setPen(QPen(col, 1.0))
            painter.drawRoundedRect(pill, 4, 4)
            painter.setPen(QColor("#f8fafc"))
            painter.drawText(pill, Qt.AlignCenter, self.edge.label)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemSelectedHasChanged and bool(value):
            if self._on_select:
                self._on_select(self.edge.detail or self.edge.label)
        return super().itemChange(change, value)


class ProcessGraphView(QGraphicsView):
    """Interactive zoomable, pannable, draggable vector canvas for process models."""

    item_inspected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setStyleSheet("background-color: #0b1120; border: 1px solid #334155; border-radius: 6px;")

        self._node_items: Dict[str, DraggableNodeItem] = {}

    def render_discovery(self, result: DiscoveryResult) -> None:
        self._scene.clear()
        self._node_items.clear()

        if not result.nodes:
            return

        for node in result.nodes:
            item = DraggableNodeItem(node, on_select=self.item_inspected.emit)
            self._scene.addItem(item)
            self._node_items[node.id] = item

        edge_pairs = {(e.source, e.target) for e in result.edges}
        for edge in result.edges:
            src_item = self._node_items.get(edge.source)
            tgt_item = self._node_items.get(edge.target)
            if src_item is None or tgt_item is None:
                continue
            has_reverse = (edge.target, edge.source) in edge_pairs and edge.source != edge.target
            offset = 32.0 if has_reverse else 0.0
            e_item = CurvedEdgeItem(
                edge,
                src_item,
                tgt_item,
                curve_offset=offset,
                on_select=self.item_inspected.emit,
            )
            self._scene.addItem(e_item)

        bounds = self._scene.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        self._scene.setSceneRect(bounds)
        self.fit_graph()

    def fit_graph(self) -> None:
        if self._scene.items():
            bounds = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
            self.fitInView(bounds, Qt.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def export_png(self, file_path: str) -> None:
        bounds = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if bounds.isEmpty():
            return
        scale = 2.0
        w = max(800, min(6000, int(bounds.width() * scale)))
        h = max(500, min(4000, int(bounds.height() * scale)))
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("#0b1120"))
        painter = QPainter(img)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self._scene.render(painter, QRectF(0, 0, w, h), bounds)
        painter.end()
        img.save(file_path, "PNG")
