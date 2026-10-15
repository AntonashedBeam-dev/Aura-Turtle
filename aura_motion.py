#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA · motion graphics на чистом turtle
=======================================
Только стандартная библиотека Python (turtle, math, random, time).

Сцены
-----
 1. BIG BANG  — конечная: «вдох» частиц → взрыв, ударные волны, искры, тряска камеры
 2. MORPH     — конечная: неоновая фигура морфится круг → треугольник → квадрат → звезда,
                схлопывается и «разрезает» экран световой линией
 3. ORBIT     — цикл: 3D-сфера из частиц с кольцом (перспектива, сортировка по глубине)
 4. SIGNAL    — цикл: «живые» неоновые звуковые волны с бегущими огоньками
 5. AURA      — сборка логотипа из частиц → неоновая обводка → вспышка → орбита,
                затем бесконечная «дышащая» анимация

Управление
----------
 ← / →    предыдущая / следующая сцена        1..5   перейти к сцене
 Space    пауза                               A      автопоказ вкл/выкл
 R        начать сначала                      F      показать FPS
 H        служебные надписи вкл/выкл          Esc    выход

Запуск
------
 python3 aura_motion.py               обычное окно 1100×700
 python3 aura_motion.py --vertical    вертикальный кадр 9:16 (Reels / Shorts / TikTok)
 python3 aura_motion.py --reel        режим записи: 9:16, без надписей,
                                      чёрный экран до нажатия Space (R — снова чёрный экран)
 --size 1080x1920                     точный размер окна в пикселях
 --loop 6                             сколько секунд показывать каждый цикл

Рендер в видео (без OBS, ровно 30 к/с, родное разрешение 1080×1920)
 python3 aura_motion.py --render reel.mp4
 python3 aura_motion.py --render logo.mp4 --scenes 5 --tail 10
   --scenes 5,3,4   какие сцены и в каком порядке      --tail 8   сколько секунд «живёт» логотип
   --fps 30         частота кадров                     --size     размер видео (по умолчанию 1080x1920)
 Нужны внешние программы (не библиотеки Python): Xvfb, ffmpeg, ImageMagick
   sudo apt install xvfb ffmpeg imagemagick

Как это сделано (чтобы не выглядело как turtle)
-----------------------------------------------
 * tracer(0) + ручной update(): кадр рисуется целиком и показывается разом, 60 к/с.
 * Время — настоящее (perf_counter), анимации описаны функциями от времени
   и кривыми плавности (easing), а не «шагами черепашки».
 * «Прозрачность» имитируется смешиванием цвета с фоном — так сделаны свечение
   (несколько слоёв линий разной толщины), затухания и переходы между сценами.
 * Свечение рисуется послойно для всех объектов сразу, чтобы ореол одного
   объекта не перекрывал яркую сердцевину другого.
"""

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import time
import tkinter
import turtle

# ───────────────────────────── настройки ──────────────────────────────
W, H = 1100, 700       # логический размер кадра (в нём описаны все сцены)
K = 1.0                # масштаб: пиксели окна / логические единицы
PIXEL_SIZE = None      # точный размер окна, если задан --size
SHOW_HUD = True        # служебные надписи
WAIT = False           # ждать Space перед стартом (для записи)
FPS = 60
TRANS = 0.4            # длительность затемнения между сценами, сек
LOOP_SHOW = 9.0        # сколько секунд показывать цикл в автопоказе

BG = (6, 7, 16)
WHITE = (255, 255, 255)
CYAN = (0, 225, 255)
VIOLET = (125, 80, 255)
PINK = (255, 64, 170)
BLUE = (70, 130, 255)
PALETTE = (CYAN, VIOLET, PINK, CYAN)

TAU = math.tau
FADE = 1.0             # глобальная «непрозрачность» текущей сцены
SHAKE = [0.0, 0.0]     # смещение камеры (тряска)


# ───────────────────────────── математика ─────────────────────────────
def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return a + (b - a) * t


def prog(t, start, dur):
    """Прогресс 0..1 отрезка анимации, который начинается в start и длится dur."""
    return clamp((t - start) / dur)


def ease_in_cubic(p):
    return p * p * p


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_in_out_cubic(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_expo(p):
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def ease_out_back(p, s=1.70158):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def ease_in_back(p, s=1.70158):
    return (s + 1) * p ** 3 - s * p ** 2


# ───────────────────────────── цвет ───────────────────────────────────
def mix(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t)


def hexc(rgb):
    # цвет квантуется с шагом 4: меньше уникальных цветов → Tk реже выделяет новые
    return "#%02x%02x%02x" % tuple(int(clamp(v, 0, 255)) & 0xFC for v in rgb)


def col(rgb, a=1.0):
    """Цвет с «альфой»: смешиваем с фоном. Почти невидимое не рисуем вовсе (None)."""
    a = clamp(a * FADE)
    if a < 0.025:
        return None
    return hexc(mix(BG, rgb, a))


def grad(u):
    """Циклический фирменный градиент cyan → violet → pink → cyan."""
    u = (u % 1.0) * 3
    i = int(u)
    return mix(PALETTE[i], PALETTE[i + 1], u - i)


# ───────────────────────────── кисть ──────────────────────────────────
class Pen:
    """Тонкая обёртка над одной черепашкой.
    Кеширует цвет и толщину (каждая смена стиля в turtle — это лишний вызов Tk)."""

    def __init__(self):
        t = turtle.Turtle(visible=False)
        t.speed(0)
        t.setundobuffer(None)   # без истории undo — заметно быстрее
        t.penup()
        self.t, self.c, self.w = t, None, None

    def _style(self, c, w):
        if c != self.c:
            self.t.pencolor(c)
            self.c = c
        if w != self.w:
            self.t.pensize(w)
            self.w = w

    def line(self, pts, c, w):
        if c is None or len(pts) < 2:
            return
        self._style(c, max(0.5, round(w * K * 2) / 2))
        t, (sx, sy), k = self.t, SHAKE, K
        x, y = pts[0]
        t.goto((x + sx) * k, (y + sy) * k)
        t.pendown()
        for x, y in pts[1:]:
            t.goto((x + sx) * k, (y + sy) * k)
        t.penup()

    def dot(self, x, y, size, c):
        """Точка = отрезок нулевой длины с круглыми концами (так работает и turtle.dot)."""
        size *= K
        if c is None or size < 1:
            return
        self._style(c, round(size * 2) / 2)
        t = self.t
        x = (x + SHAKE[0]) * K
        y = (y + SHAKE[1]) * K
        t.goto(x, y)
        t.pendown()
        t.goto(x, y)
        t.penup()

    def poly(self, pts, c):
        if c is None or len(pts) < 3:
            return
        t, (sx, sy), k = self.t, SHAKE, K
        t.fillcolor(c)
        t.goto((pts[0][0] + sx) * k, (pts[0][1] + sy) * k)
        t.begin_fill()
        for x, y in pts[1:]:
            t.goto((x + sx) * k, (y + sy) * k)
        t.end_fill()

    def text(self, x, y, s, c, size=12, weight="normal", align="center", family="Helvetica"):
        if c is None:
            return
        self._style(c, self.w or 1)
        self.t.goto((x + SHAKE[0]) * K, (y + SHAKE[1]) * K)
        self.t.write(s, align=align, font=(family, max(1, round(size * K)), weight))

    def clear(self):
        self.t.clear()


def glow_lines(pen, items, layers=((5.0, 0.09), (2.6, 0.24)), core_white=0.5):
    """items: [(точки, rgb, толщина, альфа)].
    Сначала рисуем все слои свечения всех объектов, потом все яркие сердцевины."""
    for k, la in layers:
        for pts, rgb, w, a in items:
            pen.line(pts, col(rgb, a * la), w * k)
    for pts, rgb, w, a in items:
        pen.line(pts, col(mix(rgb, WHITE, core_white), a), w)


def radial(pen, x, y, size, rgb, a=1.0, steps=6):
    """Мягкое радиальное пятно: стопка кругов, к центру всё ярче."""
    for i in range(steps):
        pen.dot(x, y, size * (1 - i / steps), col(rgb, a * ((i + 1) / steps) ** 1.6))


def glow_dot(pen, x, y, size, rgb, a=1.0):
    pen.dot(x, y, size * 3.0, col(rgb, a * 0.10))
    pen.dot(x, y, size * 1.7, col(rgb, a * 0.30))
    pen.dot(x, y, size, col(mix(rgb, WHITE, 0.6), a))


# ───────────────────────────── геометрия ──────────────────────────────
def ring_pts(cx, cy, rx, ry=None, n=48, a0=0.0, a1=TAU, tilt=0.0):
    ry = rx if ry is None else ry
    ct, st = math.cos(tilt), math.sin(tilt)
    out = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * ct - y * st, cy + x * st + y * ct))
    return out


def chunks(pts, n):
    """Режем ломаную на куски по n сегментов (соседние куски делят одну точку)."""
    return [pts[i:i + n + 1] for i in range(0, len(pts) - 1, n)]


def resample(poly, n):
    """Равномерно расставляет n точек по периметру замкнутого многоугольника."""
    segs, total = [], 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = math.dist(a, b)
        segs.append((a, b, d))
        total += d
    out, i, acc = [], 0, 0.0
    for k in range(n):
        target = total * k / n
        while i < len(segs) - 1 and acc + segs[i][2] < target:
            acc += segs[i][2]
            i += 1
        a, b, d = segs[i]
        u = (target - acc) / d if d else 0
        out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
    return out


def densify(pts, step):
    """Добавляет промежуточные точки, чтобы расстояние между ними было ≈ step."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, round(math.dist(a, b) / step))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


def arc(cx, cy, r, a0, a1, n=18):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


# ───────────────────────────── сцены ──────────────────────────────────
class Scene:
    title = ""
    kind = "LOOP"
    duration = None      # для конечных сцен — длительность в секундах
    auto = LOOP_SHOW     # для циклов — сколько показывать в автопоказе

    def reset(self):
        pass

    def draw(self, pen, t):
        pass


class BigBang(Scene):
    """Конечная №1: частицы стягиваются в ядро → взрыв."""
    title, kind, duration = "BIG BANG", "ONE-SHOT", 4.0
    BOOM = 1.15

    def reset(self):
        rnd = random.Random(7)
        self.inhale = [(rnd.uniform(0, TAU), rnd.uniform(170, 480), rnd.uniform(0, 0.5), rnd.random())
                       for _ in range(64)]
        self.sparks = [(rnd.uniform(0, TAU), rnd.uniform(160, 640) * rnd.random() ** 0.35,
                        rnd.uniform(1.0, 2.5), rnd.uniform(1.4, 4.0), rnd.uniform(-0.7, 0.7))
                       for _ in range(140)]

    def draw(self, pen, t):
        B = self.BOOM
        cos, sin = math.cos, math.sin

        # ── 1. вдох: частицы по спирали затягивает в центр
        if t < B + 0.05:
            p = clamp(t / B)
            s = 4 + 30 * ease_in_cubic(p) + 3 * sin(t * 42) * p
            core = mix(VIOLET, WHITE, p * 0.8)
            radial(pen, 0, 0, s * 4, core, 0.45 * (0.35 + 0.65 * p), steps=4)
            for a, r0, d, u in self.inhale:
                p = prog(t, d, B - d)
                if p <= 0:
                    continue
                e, e0 = ease_in_cubic(p), ease_in_cubic(max(0.0, p - 0.12))
                r1, r2 = r0 * (1 - e), r0 * (1 - e0)
                a1, a2 = a + e * 1.8, a + e0 * 1.8
                pen.line([(r2 * cos(a2), r2 * sin(a2)), (r1 * cos(a1), r1 * sin(a1))],
                         col(grad(u), 0.25 + 0.75 * p), 1.2 + 2.2 * p)
            pen.dot(0, 0, s * 1.6, col(core, 0.4 + 0.4 * p))
            pen.dot(0, 0, s, col(mix(core, WHITE, 0.6), 0.5 + 0.5 * p))
            return

        # ── 2. взрыв
        tb = t - B
        k = max(0.0, 1 - tb / 0.6) ** 2
        SHAKE[0], SHAKE[1] = random.uniform(-1, 1) * 18 * k, random.uniform(-1, 1) * 18 * k

        p = prog(tb, 0, 0.45)                                  # вспышка
        if p < 1:
            radial(pen, 0, 0, lerp(120, 1500, ease_out_expo(p)), mix(VIOLET, WHITE, 0.5), 0.5 * (1 - p) ** 2, 11)

        rings = []                                             # ударные волны
        for i, (dl, rgb) in enumerate(((0.0, CYAN), (0.09, VIOLET), (0.2, PINK))):
            p = prog(tb, dl, 1.8)
            if p <= 0 or p >= 1:
                continue
            r = 20 + 600 * ease_out_expo(p)
            a, w = (1 - p) ** 1.5, 1 + 7 * (1 - p)
            if i == 1:                                         # пунктирное «HUD»-кольцо
                rot = tb * 1.6
                for j in range(12):
                    a0 = rot + j * TAU / 12
                    rings.append((ring_pts(0, 0, r, n=6, a0=a0, a1=a0 + TAU / 12 * 0.55), rgb, w * 0.8, a))
            else:
                rings.append((ring_pts(0, 0, r, n=60), rgb, w, a))
        glow_lines(pen, rings, layers=((2.8, 0.22),))

        for a0, dist, life, w0, curl in self.sparks:          # искры со «смазом»
            p = prog(tb, 0, life)
            if p >= 1:
                continue
            pts = []
            for q in (max(0.0, p - 0.07), p):
                e = ease_out_expo(q)
                ang, r = a0 + curl * e, dist * e
                pts.append((r * cos(ang), r * sin(ang) - 70 * q * q))
            c = mix(grad(a0 / TAU), WHITE, (1 - p) ** 3 * 0.8)
            pen.line(pts, col(c, (1 - p) ** 1.2), w0 * (1 - p * 0.7))

        p = prog(tb, 0, 1.0)                                   # остывающее ядро
        if p < 1:
            s = 22 * (1 - p) + 2
            if p > 0.4:
                radial(pen, 0, 0, s * 3.5, VIOLET, (1 - p) * 0.5, steps=3)
            pen.dot(0, 0, s, col(mix(VIOLET, WHITE, 1 - p * 0.6), 1 - p))


class Morph(Scene):
    """Конечная №2: морфинг неоновой фигуры и световой «разрез»."""
    title, kind, duration = "MORPH", "ONE-SHOT", 5.8
    N = 120
    T0, STEP, MD = 0.55, 0.95, 0.6

    def reset(self):
        n = self.N

        def regular(k, inner=None):
            m = k * 2 if inner else k
            v = []
            for i in range(m):
                a = math.pi / 2 - TAU * i / m
                r = inner if (inner and i % 2) else 1.0
                v.append((r * math.cos(a), r * math.sin(a)))
            return resample(v, n)

        circle = [(math.cos(math.pi / 2 - TAU * i / n), math.sin(math.pi / 2 - TAU * i / n)) for i in range(n)]
        self.shapes = [circle, regular(3), regular(4), regular(5, 0.42), circle]

    def geom(self, t):
        cur, spin = self.shapes[0], 0.0
        for i in range(4):
            p = ease_in_out_cubic(prog(t, self.T0 + i * self.STEP, self.MD))
            if p <= 0:
                break
            a, b = self.shapes[i], self.shapes[i + 1]
            cur = b if p >= 1 else [(x1 + (x2 - x1) * p, y1 + (y2 - y1) * p) for (x1, y1), (x2, y2) in zip(a, b)]
            spin += p
        rot = t * 0.5 + spin * TAU / 6
        s = 175 * ease_out_back(prog(t, 0, 0.7)) * (1 + 0.05 * math.sin(t * 4))
        s *= max(0.0, 1 - ease_in_back(prog(t, 4.1, 0.5)))
        c, sn = math.cos(rot) * s, math.sin(rot) * s
        return [(x * c - y * sn, x * sn + y * c) for x, y in cur], s

    def draw(self, pen, t):
        pts, s = self.geom(t)

        # эхо-копии с запаздыванием (как motion trail в After Effects)
        for j in (3, 2, 1):
            e, _ = self.geom(max(0.0, t - j * 0.07))
            k = 1 + 0.07 * j
            e = [(x * k, y * k) for x, y in e[::2]]
            pen.line(e + e[:1], col(grad(t * 0.2 + j * 0.12), 0.26 - j * 0.06), 1.3)

        # основная фигура: градиент бежит по контуру
        if s > 1:
            closed = pts + pts[:1]
            parts = chunks(closed, 10)
            items = [(ch, grad(i / len(parts) + t * 0.3), 2.6, 1.0) for i, ch in enumerate(parts)]
            glow_lines(pen, items, layers=((4.6, 0.09), (2.4, 0.26)))

            # спутники на орбите
            for j in range(3):
                a = -t * 1.8 + j * TAU / 3
                R = s * 1.45
                trail = [(R * math.cos(a + q * 0.06), R * math.sin(a + q * 0.06)) for q in range(10)]
                pen.line(trail, col(grad(j / 3 + t * 0.2), 0.35), 2)
                glow_dot(pen, trail[0][0], trail[0][1], 5, grad(j / 3 + t * 0.2))

        # световой разрез экрана
        p = prog(t, 4.45, 1.0)
        if p > 0:
            x = 600 * ease_out_expo(p)
            a = 1 - prog(t, 5.0, 0.7)
            glow_lines(pen, [([(-x, 0), (x, 0)], mix(CYAN, VIOLET, p), 0.6 + 2.6 * (1 - p), a)],
                       layers=((6, 0.08), (3, 0.25)))
            glow_dot(pen, -x, 0, 6, CYAN, a)
            glow_dot(pen, x, 0, 6, PINK, a)


class Orbit(Scene):
    """Цикл №1: 3D-сфера из частиц, «дышащая» шумом, с наклонным кольцом."""
    title, kind = "ORBIT", "LOOP"

    def reset(self):
        n, ga = 190, math.pi * (3 - math.sqrt(5))     # сфера Фибоначчи — равномерные точки
        self.sphere = []
        for i in range(n):
            y = 1 - 2 * (i + 0.5) / n
            r = math.sqrt(1 - y * y)
            self.sphere.append((math.cos(ga * i) * r, y, math.sin(ga * i) * r))
        self.ring = [TAU * i / 80 for i in range(80)]
        self.rr = 1.55 if W >= H else 1.3                 # в вертикали кольцо компактнее

    def draw(self, pen, t):
        cos, sin = math.cos, math.sin
        R = min(165, (W / 2 - 20) / (self.rr * 1.5)) * ease_out_back(prog(t, 0, 1.1))
        ay, ax = t * 0.55, 0.42 + 0.12 * sin(t * 0.45)
        cy_, sy_, cx_, sx_ = cos(ay), sin(ay), cos(ax), sin(ax)
        D = 4.5

        def proj(x, y, z):
            x1, z1 = x * cy_ + z * sy_, -x * sy_ + z * cy_
            y2, z2 = y * cx_ - z1 * sx_, y * sx_ + z1 * cx_
            f = D / (D - z2)
            return x1 * R * f, y2 * R * f, z2

        radial(pen, 0, 0, 3.9 * R, VIOLET, 0.13, steps=7)     # мягкий ореол

        items = []
        for x, y, z in self.sphere:
            k = 1 + 0.11 * sin(3 * x + t * 2.1) * sin(3 * y + t * 1.7) + 0.05 * sin(5 * z - t * 2.6)
            px, py, pz = proj(x * k, y * k, z * k)
            items.append((pz, px, py, 0, y))

        tilt, rr = 0.5, self.rr
        ct, st = cos(tilt), sin(tilt)
        for a in self.ring:
            aa = a + t * 0.9
            x, z = rr * cos(aa), rr * sin(aa)
            px, py, pz = proj(x * ct, x * st, z)
            items.append((pz, px, py, 1, 0))
        for j in range(2):                                           # «луны» на кольце
            aa = t * 0.9 * 1.6 + j * math.pi
            x, z = rr * cos(aa), rr * sin(aa)
            px, py, pz = proj(x * ct, x * st, z)
            items.append((pz, px, py, 2, j))

        # painter's algorithm: дальние точки рисуем первыми.
        # Глубину и цвет квантуем, чтобы соседние точки делили один стиль кисти.
        items.sort(key=lambda it: (int(clamp((it[0] + 1.6) / 3.2) * 12), it[3], round(it[4] * 4)))
        for pz, px, py, kind, extra in items:
            d = int(clamp((pz + 1.6) / 3.2) * 12) / 12
            if kind == 0:
                band = round(extra * 4) / 4
                pen.dot(px, py, 1.5 + 5.5 * d, col(grad(0.55 + 0.3 * band + t * 0.05), 0.15 + 0.85 * d ** 1.4))
            elif kind == 1:
                pen.dot(px, py, 1.2 + 2.6 * d, col(mix(CYAN, WHITE, 0.3), 0.1 + 0.8 * d))
            else:
                glow_dot(pen, px, py, 4 + 6 * d, PINK if extra else CYAN, 0.35 + 0.65 * d)


class Signal(Scene):
    """Цикл №2: неоновые звуковые волны (в духе голосовых ассистентов)."""
    title, kind = "SIGNAL", "LOOP"
    WAVES = (  # цвет, амплитуда, частота, скорость, фаза, толщина
        (CYAN, 1.00, 1.6, 2.3, 0.0, 2.6),
        (VIOLET, 0.80, 2.3, -1.8, 1.3, 2.2),
        (PINK, 0.65, 3.1, 2.9, 2.6, 1.8),
        (BLUE, 0.50, 4.3, -3.5, 0.7, 1.4),
    )

    def reset(self):
        self.L = L = min(480, W / 2 - 40)
        self.amp = 150 if W >= H else 200        # в вертикальном кадре волны выше
        n = 90
        self.xs = [-L + 2 * L * i / (n - 1) for i in range(n)]
        self.env = [(1 - (x / L) ** 2) ** 2.5 for x in self.xs]
        rnd = random.Random(5)
        self.riders = [(rnd.randrange(4), rnd.uniform(0.12, 0.3) * rnd.choice((-1, 1)), rnd.random())
                       for _ in range(12)]

    def wave_y(self, i, x, env, t):
        rgb, amp, fr, sp, ph, w = self.WAVES[i]
        A = self.amp * amp * ease_out_cubic(prog(t, 0, 1.2)) * (0.55 + 0.45 * math.sin(t * (0.9 + 0.37 * i) + ph * 2))
        return A * env * math.sin(fr * x / self.L * math.pi + sp * t + ph)

    def draw(self, pen, t):
        L = self.L
        waves = []
        for i, (rgb, amp, fr, sp, ph, w) in enumerate(self.WAVES):
            pts = [(x, self.wave_y(i, x, e, t)) for x, e in zip(self.xs, self.env)]
            waves.append((pts, rgb, w, 1.0))

        # полупрозрачная «заливка» волн — сзади всего
        for pts, rgb, w, a in waves[:3]:
            pen.poly(pts + [(L, 0), (-L, 0)], col(rgb, 0.07))

        pen.line([(-L - 40, 0), (L + 40, 0)], col(VIOLET, 0.25), 1)
        glow_lines(pen, waves, layers=((4.2, 0.08), (2.2, 0.22)))

        for wi, sp, off in self.riders:                              # огоньки бегут по волнам
            u = (off + t * sp) % 1.0
            x = (u * 2 - 1) * L
            env = (1 - (x / L) ** 2) ** 2.5
            y = self.wave_y(wi, x, env, t)
            glow_dot(pen, x, y, 2.5 + 3 * env, self.WAVES[wi][0], 0.2 + 0.8 * env)


# ── буквы логотипа: ширина и штрихи в единицах высоты буквы
LETTERS = {
    "A": (0.82, [[(0, 0), (0.41, 1), (0.82, 0)], [(0.2, 0.36), (0.62, 0.36)]]),
    "U": (0.72, [[(0, 1), (0, 0.36)] + arc(0.36, 0.36, 0.36, 180, 360)[1:] + [(0.72, 1)]]),
    "R": (0.72, [[(0, 0), (0, 1), (0.38, 1)] + arc(0.38, 0.74, 0.26, 90, -90)[1:] + [(0, 0.48)],
                 [(0.3, 0.48), (0.72, 0)]]),
}


class Logo(Scene):
    """Финал: логотип AURA собирается из частиц, затем живёт бесконечно."""
    title, kind, auto = "AURA", "BUILD → LOOP", None
    S, GAP = 116, 0.3
    T_DRAW, T_FLASH, T_RING, T_SUB, T_IDLE = 1.35, 2.75, 2.75, 3.25, 3.8

    def reset(self):
        S, word = self.S, "AURA"
        total = sum(LETTERS[c][0] for c in word) + self.GAP * (len(word) - 1)
        ox, oy = -total * S / 2, -S / 2 + 30
        self.cy = oy + S / 2
        self.left, self.width = ox, total * S
        self.paths, x0 = [], 0.0
        for c in word:
            w, strokes = LETTERS[c]
            for st in strokes:
                self.paths.append(densify([(ox + (x0 + px) * S, oy + py * S) for px, py in st], 8))
            x0 += w + self.GAP

        rnd = random.Random(3)
        self.parts = []
        for path in self.paths:
            for tx, ty in path:
                u = (tx - ox) / self.width
                self.parts.append((tx, ty, rnd.uniform(0, TAU), rnd.uniform(450, 850), rnd.uniform(2.2, 3.8),
                                   0.05 + 0.6 * u + rnd.uniform(0, 0.25), rnd.uniform(0.95, 1.3), u))
        span = min(430, W / 2 - 30)
        self.sparkles = [(rnd.uniform(-span, span), rnd.random(), rnd.uniform(0.06, 0.16), rnd.uniform(0, TAU))
                         for _ in range(30)]
        self.rx, self.ry, self.tilt = min(350, W / 2 - 22), 88, -0.12

    def ell(self, th):
        x, y = self.rx * math.cos(th), self.ry * math.sin(th)
        ct, st = math.cos(self.tilt), math.sin(self.tilt)
        return x * ct - y * st, self.cy - 4 + x * st + y * ct

    def ring_half(self, pen, t, front, rp):
        """Задняя половина орбиты рисуется до букв, передняя — после: эффект объёма."""
        if rp <= 0:
            return
        if front:
            a0, a1, alpha = math.pi, math.pi * (1 + rp), 1.0
        else:
            a0, a1, alpha = math.pi * (1 - rp), math.pi, 0.45
        n = 48
        pts = [self.ell(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
        parts = chunks(pts, 8)
        items = [(ch, grad(i / len(parts) * 0.5 + (0.5 if front else 0) + t * 0.1), 1.6, alpha)
                 for i, ch in enumerate(parts)]
        glow_lines(pen, items, layers=((3.2, 0.2),))

    def comet(self, pen, t, front):
        ca = prog(t, self.T_IDLE, 0.6)
        if ca <= 0:
            return
        th0 = math.pi + (t - self.T_IDLE) * 1.25
        for k in range(10, -1, -1):
            th = th0 - k * 0.05
            is_front = math.sin(th) < 0
            if is_front != front:
                continue
            x, y = self.ell(th)
            f = 1 - k / 11
            a = ca * f * (1.0 if front else 0.4)
            if k == 0:
                glow_dot(pen, x, y, 6, mix(CYAN, WHITE, 0.3), a)
            else:
                pen.dot(x, y, 7 * f + 1, col(grad(k / 22 + t * 0.1), a))

    def draw(self, pen, t):
        cos, sin = math.cos, math.sin
        cy = self.cy
        breath = 1 + 0.25 * sin(t * 2.2)

        # мягкий ореол позади логотипа
        ha = prog(t, self.T_FLASH, 0.8) * (0.85 + 0.15 * breath)
        if ha > 0:
            for i in range(6):                                   # эллиптический градиент
                f = 1 - i / 6
                pen.poly(ring_pts(0, cy, 560 * f, 230 * f, n=28)[:-1], col(VIOLET, 0.11 * ha * ((i + 1) / 6) ** 1.4))

        # «зажигание» букв и ударная волна в момент сборки
        p = prog(t, self.T_FLASH, 0.7)
        ignite = (1 - p) ** 2 if p > 0 else 0.0
        if 0 < p < 1:
            SHAKE[0], SHAKE[1] = random.uniform(-1, 1) * 8 * ignite, random.uniform(-1, 1) * 8 * ignite
        p = prog(t, self.T_FLASH, 1.2)
        if 0 < p < 1:
            rx = lerp(150, 950, ease_out_expo(p))
            glow_lines(pen, [(ring_pts(0, cy, rx, rx * 0.26, n=64), CYAN, 1 + 3 * (1 - p), (1 - p) ** 1.5)],
                       layers=((3, 0.2),))

        rp = ease_in_out_cubic(prog(t, self.T_RING, 1.1))
        self.ring_half(pen, t, False, rp)
        self.comet(pen, t, False)

        # частицы летят по спиралям к своим местам в буквах
        fa = 1 - prog(t, 2.05, 0.6)
        if fa > 0:
            for tx, ty, th0, r0, swirl, delay, dur, u in self.parts:
                p = prog(t, delay, dur)
                if p <= 0:
                    continue
                c = col(mix(grad(u * 0.6 + 0.1), WHITE, 0.25), fa * (0.3 + 0.7 * p))
                if p >= 1:
                    pen.dot(tx, ty, 3.5, c)
                    continue
                pts = []
                for q in (max(0.0, p - 0.06), p):
                    e = ease_out_cubic(q)
                    r, a = r0 * (1 - e), th0 + swirl * (1 - e)
                    pts.append((tx + r * cos(a), ty + r * sin(a)))
                pen.line(pts, c, 1.5 + 1.5 * p)

        # неоновые буквы
        glow, cores, tips = [], [], []
        shine_x = None
        sp = ((t - 4.2) % 4.0) / 1.2 if t > 4.2 else 2
        if sp < 1:
            shine_x = lerp(-560, 560, ease_in_out_cubic(sp))
        for j, path in enumerate(self.paths):
            p = ease_in_out_cubic(prog(t, self.T_DRAW + 0.1 * j, 0.75))
            if p <= 0:
                continue
            n = len(path)
            f = p * (n - 1)
            k = int(f)
            pts = path[:k + 1]
            if k < n - 1:
                (x1, y1), (x2, y2) = path[k], path[k + 1]
                tip = (x1 + (x2 - x1) * (f - k), y1 + (y2 - y1) * (f - k))
                pts = pts + [tip]
                tips.append(tip)
            if len(pts) < 2:
                continue
            mx = sum(x for x, _ in path) / n
            glow.append((pts, grad((mx - self.left) / self.width * 0.6 + 0.1 - t * 0.08)))
            for ch in chunks(pts, 4):
                cx = ch[len(ch) // 2][0]
                c = grad((cx - self.left) / self.width * 0.6 + 0.1 - t * 0.08)
                sh = math.exp(-((cx - shine_x) / 55) ** 2) if shine_x is not None else 0
                cores.append((ch, mix(mix(c, WHITE, 0.35), WHITE, sh)))
        g = (1.0 if t < self.T_IDLE else breath) + 2.2 * ignite
        for k, la in ((6.0, 0.07 * g), (3.4, 0.16 * g), (1.9, 0.55 + 0.4 * ignite)):
            for pts, c in glow:
                pen.line(pts, col(mix(c, WHITE, 0.4 * ignite), la), 3.2 * k)
        for ch, c in cores:
            pen.line(ch, col(mix(c, WHITE, ignite), 1.0), 3.2)
        for x, y in tips:
            glow_dot(pen, x, y, 6, mix(CYAN, WHITE, 0.5))

        self.ring_half(pen, t, True, rp)
        self.comet(pen, t, True)

        # подпись L A B с «разъезжающимся» трекингом
        p = ease_out_expo(prog(t, self.T_SUB, 1.3))
        a = prog(t, self.T_SUB, 0.6)
        if a > 0:
            y = cy - 132
            sp_ = lerp(70, 26, p)
            for i, ch in enumerate("LAB"):
                pen.text((i - 1) * sp_, y, ch, col(mix(VIOLET, WHITE, 0.8), a), 20, "bold")
            x0, ln = sp_ * 1.5 + 18, lerp(0, 150, p)
            for d in (-1, 1):
                pen.line([(d * x0, y + 13), (d * (x0 + ln), y + 13)], col(VIOLET, a * 0.8), 1.5)

        # искры, медленно всплывающие вокруг
        ia = prog(t, self.T_IDLE, 1.0)
        if ia > 0:
            for x, ph, spd, tw in self.sparkles:
                u = (ph + t * spd) % 1.0
                y = cy - 170 + u * 340
                a = ia * sin(math.pi * u) * (0.5 + 0.5 * sin(t * 3 + tw))
                pen.dot(x, y, 2.5, col(grad((x + 430) / 860 * 0.6), a))

        a = prog(t, 5.6, 1.2)
        if a > 0:
            pen.text(0, -268, "100% Python · import turtle · ни одной сторонней библиотеки",
                     col((150, 150, 190), a * 0.7), 10, family="Courier")


# ───────────────────────────── приложение ─────────────────────────────
def draw_backdrop(pen):
    """Статичный фон рисуется один раз отдельной черепашкой и не стирается."""
    global FADE
    FADE = 1.0
    for i in range(12, 0, -1):
        r = i / 12
        pen.dot(0, 0, max(W, H) * 1.4 * r, hexc(mix(BG, (13, 12, 30), (1 - r) ** 1.3)))
    rnd = random.Random(11)
    for _ in range(int(140 * W * H / (1100 * 700))):
        z = rnd.random()
        pen.dot(rnd.uniform(-W / 2, W / 2), rnd.uniform(-H / 2, H / 2), 1 + 1.6 * z,
                hexc(mix(BG, (170, 180, 255), 0.12 + 0.4 * z ** 2)))


class App:
    def __init__(self, live=True, scenes=None):
        global K
        s = self.screen = turtle.Screen()
        if PIXEL_SIZE:
            wpx, hpx = PIXEL_SIZE
        else:                                   # вписываем кадр в экран монитора
            cv = s.getcanvas()
            k = min(1.0, (cv.winfo_screenwidth() - 40) / W, (cv.winfo_screenheight() - 110) / H)
            wpx, hpx = int(W * k) // 2 * 2, int(H * k) // 2 * 2
        K = wpx / W
        if live:
            s.setup(wpx, hpx)
        else:                                   # рендер: окно ровно в левом верхнем углу виртуального экрана
            s.setup(wpx, hpx, startx=0, starty=0)
        self.size = (wpx, hpx)
        s.title("AURA · motion graphics на turtle")
        s.bgcolor(hexc(BG))
        s.tracer(0, 0)
        try:
            cv = s.getcanvas()
            cv.config(highlightthickness=0, borderwidth=0)
            # холст turtle лежит в рамке с отступом 1 px; config() обёртки уходит во внутренний холст,
            # поэтому цвет самой рамки задаём напрямую — иначе по краю кадра видна светлая линия
            tkinter.Frame.configure(cv, bg=hexc(BG))
            cv.winfo_toplevel().configure(bg=hexc(BG))
        except tkinter.TclError:
            pass

        draw_backdrop(Pen())
        # две кисти по очереди: старый кадр стирается ПОСЛЕ отрисовки нового,
        # поэтому Tk не освобождает и не выделяет заново одни и те же цвета
        self.pens, self.flip = [Pen(), Pen()], 0
        self.scenes = scenes or [BigBang(), Morph(), Orbit(), Signal(), Logo()]
        self.i, self.t, self.target, self.trans = 0, 0.0, None, 0.0
        self.paused, self.auto, self.show_fps = False, True, False
        self.hud_on, self.started = SHOW_HUD, not WAIT
        self.scenes[0].reset()
        self.fps, self._frames, self._fps_t = 0.0, 0, time.perf_counter()
        if not live:                            # рендер в файл: кадры подаёт render_video()
            self.started, self.hud_on, self.running = True, False, False
            return

        keys = {"Right": lambda: self.go(self.i + 1), "Left": lambda: self.go(self.i - 1),
                "space": self.toggle_pause, "Return": self.toggle_pause, "a": self.toggle_auto,
                "r": self.restart, "f": self.toggle_fps, "h": self.toggle_hud, "Escape": self.quit}
        for k, fn in keys.items():
            s.onkey(fn, k)
        for j in range(len(self.scenes)):
            s.onkey(lambda j=j: self.go(j), str(j + 1))
        s.listen()

        self.running = True
        self.last = time.perf_counter()
        self.tick()

    # управление
    def go(self, j):
        self.target = j % len(self.scenes)
        self.trans = 0.0

    def toggle_pause(self):
        if not self.started:                    # режим записи: старт по Space
            self.started, self.t = True, 0.0
            return
        self.paused = not self.paused

    def restart(self):
        if WAIT:                                # снова чёрный экран, ждём Space — удобно для дублей
            self.started, self.paused, self.target, self.i, self.t = False, False, None, 0, 0.0
            self.scenes[0].reset()
        else:
            self.go(0)

    def toggle_hud(self):
        self.hud_on = not self.hud_on

    def toggle_auto(self):
        self.auto = not self.auto

    def toggle_fps(self):
        self.show_fps = not self.show_fps

    def quit(self):
        self.running = False
        try:
            self.screen.bye()
        except (turtle.Terminator, tkinter.TclError):
            pass

    # цикл кадров
    def tick(self):
        if not self.running:
            return
        start = time.perf_counter()
        dt = min(start - self.last, 0.05)
        self.last = start
        try:
            self.frame(dt)
            spent = time.perf_counter() - start
            self.screen.ontimer(self.tick, max(1, int((1 / FPS - spent) * 1000)))
        except (turtle.Terminator, tkinter.TclError):
            self.running = False

    def frame(self, dt):
        global FADE
        if not self.started:
            for p in self.pens:
                p.clear()
            self.screen.update()
            return
        if not self.paused:
            self.t += dt
        sc = self.scenes[self.i]
        out = 1.0
        if self.target is not None:                       # затемнение и смена сцены
            self.trans += dt
            out = 1 - clamp(self.trans / TRANS)
            if self.trans >= TRANS:
                self.i, self.target, self.t, out = self.target, None, 0.0, 1.0
                sc = self.scenes[self.i]
                sc.reset()
        elif sc.duration and self.t >= sc.duration and self.i < len(self.scenes) - 1:
            self.go(self.i + 1)
        elif self.auto and sc.auto and self.t >= LOOP_SHOW:
            self.go(self.i + 1)

        FADE = clamp(self.t / 0.45) * out
        SHAKE[0] = SHAKE[1] = 0.0
        self.flip ^= 1
        pen, old = self.pens[self.flip], self.pens[self.flip ^ 1]
        sc.draw(pen, self.t)
        SHAKE[0] = SHAKE[1] = 0.0
        FADE = 1.0
        if self.hud_on:
            self.hud(pen, sc)
        elif self.show_fps:
            pen.text(W / 2 - 28, H / 2 - 38, "%.0f fps" % self.fps, hexc((130, 132, 175)), 9, "bold", "right", "Courier")
        old.clear()
        self.screen.update()

        self._frames += 1
        now = time.perf_counter()
        if now - self._fps_t >= 1.0:
            self.fps = self._frames / (now - self._fps_t)
            self._frames, self._fps_t = 0, now

    def hud(self, pen, sc):
        dim, mid = hexc((70, 72, 110)), hexc((130, 132, 175))
        y = -H / 2 + 22
        pen.text(-W / 2 + 28, y, "%02d / %02d" % (self.i + 1, len(self.scenes)), mid, 10, "bold", "left", "Courier")
        pen.text(-W / 2 + 110, y, sc.title, hexc((200, 200, 235)), 10, "bold", "left", "Courier")
        pen.text(-W / 2 + 110 + 11 * len(sc.title), y, "· " + sc.kind, hexc(mix(BG, CYAN, 0.7)), 10, "normal",
                 "left", "Courier")
        state = ("ПАУЗА  " if self.paused else "") + ("АВТО" if self.auto else "РУЧНОЙ")
        if W > H:
            pen.text(W / 2 - 28, y, "←/→ сцены   1-5   SPACE пауза   A " + state + "   R заново", dim, 9,
                     "normal", "right", "Courier")
        else:
            pen.text(-W / 2 + 28, y + 22, "←/→  1-5  SPACE  A " + state + "  H скрыть", dim, 9,
                     "normal", "left", "Courier")
        pen.text(-W / 2 + 28, H / 2 - 38, "AURA LAB — motion study", dim, 9, "normal", "left", "Courier")
        if self.show_fps:
            pen.text(W / 2 - 28, H / 2 - 38, "%.0f fps" % self.fps, mid, 9, "bold", "right", "Courier")

        # полоса прогресса: для конечных — заполнение, для циклов — бегущий отрезок
        by, x0, x1 = -H / 2 + 12, -W / 2 + 28, W / 2 - 28
        pen.line([(x0, by), (x1, by)], hexc((22, 23, 42)), 2)
        if sc.duration:
            p = clamp(self.t / sc.duration)
            pen.line([(x0, by), (lerp(x0, x1, p), by)], hexc(mix(BG, CYAN, 0.8)), 2)
        else:
            u = (self.t * 0.35) % 1.0
            a, b = lerp(x0, x1, max(0.0, u - 0.12)), lerp(x0, x1, u)
            pen.line([(a, by), (b, by)], hexc(mix(BG, VIOLET, 0.9)), 2)


# ───────────────────────────── рендер в видео ─────────────────────────
SCENE_TYPES = {1: BigBang, 2: Morph, 3: Orbit, 4: Signal, 5: Logo}


def render_video(out, fps, order, tail):
    """Рисует кадры с фиксированным шагом времени и отдаёт их в ffmpeg.
    Анимация сама не знает, что её записывают: тот же App, только время идёт ровно 1/fps за кадр."""
    grab = ["magick", "import"] if shutil.which("magick") else ["import"]
    scenes = [SCENE_TYPES[n]() for n in order]
    app = App(live=False, scenes=scenes)
    w, h = app.size
    app.screen.update()

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h),
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)

    # длина каждой сцены в видео
    lengths = []
    for sc in scenes:
        if sc.duration:
            lengths.append(sc.duration)
        elif sc.auto is None:                   # логотип: сборка + «жизнь» tail секунд
            lengths.append(Logo.T_IDLE + tail)
        else:
            lengths.append(LOOP_SHOW)
    total = sum(lengths) + TRANS * (len(scenes) - 1)
    print("Рендер %s: %dx%d, %d к/с, ≈%.0f с видео" % (out, w, h, fps, total))

    dt, n, t0 = 1.0 / fps, 0, time.perf_counter()
    try:
        while True:
            last = app.i == len(scenes) - 1
            if last and app.target is None and app.t >= lengths[-1]:
                break
            if not last and app.target is None and app.t >= lengths[app.i]:
                app.go(app.i + 1)               # переход к следующей сцене из списка
            app.frame(dt if n else 0.0)
            app.screen.getcanvas().update()
            frame = subprocess.run(grab + ["-silent", "-window", "root", "-depth", "8", "rgb:-"],
                                   capture_output=True, check=True).stdout
            if len(frame) != w * h * 3:
                raise RuntimeError("снимок кадра неверного размера: %d байт" % len(frame))
            ff.stdin.write(frame)
            n += 1
            if n % fps == 0:
                el = time.perf_counter() - t0
                sys.stdout.write("\r  %5.1f / %.0f с видео   (%.0f с прошло, осталось ≈%.0f с)   " %
                                 (n / fps, total, el, el / (n / fps) * max(0.0, total - n / fps)))
                sys.stdout.flush()
    finally:
        ff.stdin.close()
        ff.wait()
    print("\nГотово: %s (%d кадров)" % (out, n))


def launch_render(args):
    """Перезапускает программу внутри невидимого экрана Xvfb ровно размером с видео:
    окно занимает весь экран, и кадр снимается целиком."""
    missing = [p for p in ("xvfb-run", "ffmpeg") if not shutil.which(p)]
    if not (shutil.which("import") or shutil.which("magick")):
        missing.append("imagemagick")
    if missing:
        print("Для рендера не хватает программ: " + ", ".join(missing))
        print("Установи:  sudo apt install xvfb ffmpeg imagemagick")
        sys.exit(1)
    w, h = PIXEL_SIZE
    env = dict(os.environ, AURA_RENDER_CHILD="1")
    cmd = ["xvfb-run", "-a", "-s", "-screen 0 %dx%dx24" % (w, h), sys.executable, os.path.abspath(__file__)]
    sys.exit(subprocess.call(cmd + sys.argv[1:], env=env))


def main():
    global W, H, PIXEL_SIZE, SHOW_HUD, WAIT, LOOP_SHOW
    ap = argparse.ArgumentParser(description="AURA · motion graphics на чистом turtle")
    ap.add_argument("--vertical", action="store_true", help="вертикальный кадр 9:16 (Reels / Shorts / TikTok)")
    ap.add_argument("--reel", action="store_true", help="режим записи: 9:16, без надписей, старт по Space")
    ap.add_argument("--clean", action="store_true", help="без служебных надписей (H — показать)")
    ap.add_argument("--size", help="точный размер окна в пикселях, например 1080x1920")
    ap.add_argument("--loop", type=float, default=LOOP_SHOW, help="сколько секунд показывать каждый цикл")
    ap.add_argument("--render", metavar="FILE.mp4", help="отрендерить в видеофайл (без OBS)")
    ap.add_argument("--fps", type=int, default=30, help="частота кадров видео при --render")
    ap.add_argument("--scenes", default="1,2,3,4,5", help="сцены для --render по порядку, например 5,3,4")
    ap.add_argument("--tail", type=float, default=8.0, help="сколько секунд логотип живёт после сборки")
    args = ap.parse_args()
    if args.render and not args.size:
        args.size = "1080x1920"

    if args.vertical or args.reel:
        W, H = 600, 1068                        # 9:16, логический кадр поуже — объекты крупнее
    if args.reel:
        SHOW_HUD, WAIT = False, True
    if args.clean:
        SHOW_HUD = False
    if args.size:
        wpx, hpx = (int(v) for v in args.size.lower().split("x"))
        PIXEL_SIZE = (wpx, hpx)
        H = 1068 if hpx > wpx else 700          # логическая высота, ширина — по пропорции окна
        W = round(H * wpx / hpx)
    LOOP_SHOW = args.loop

    if args.render:
        if not os.environ.get("AURA_RENDER_CHILD"):
            launch_render(args)
        order = [int(v) for v in args.scenes.replace(" ", "").split(",") if v]
        render_video(args.render, args.fps, order, args.tail)
        return

    App()
    turtle.mainloop()


if __name__ == "__main__":
    main()
