"""Conservative, versioned routing rules for cabinet photographs.

These are image-quality heuristics, not a learned recognizer or proof of improved
recognition. The central analysis window is a background-reduction proxy, not
an automatically detected cabinet/pack region.
"""

import cv2
import numpy as np


RULE_VERSION = "cabinet-v2"
LABELS = {"neutral": "正常或不确定：中性处理", "dark": "整体偏暗：分区提亮",
          "uneven": "局部偏暗：分区提亮", "contrast": "局部灰蒙：温和对比增强",
          "mixed": "局部偏暗与低对比：分区调整"}


def _thumbnail(image, longest_edge):
    h, w = image.shape[:2]
    scale = min(1.0, longest_edge / max(h, w))
    return cv2.resize(image, (max(4, round(w * scale)), max(4, round(h * scale))),
                      interpolation=cv2.INTER_AREA)


def analyze_regions(image):
    """Detail proxies, not OCR: only textured, non-noisy cells get local gain."""
    light = cv2.cvtColor(_thumbnail(image, 1200), cv2.COLOR_BGR2LAB)[:, :, 0]
    h, w = light.shape
    y_edges = np.linspace(int(h * .15), max(int(h * .90), int(h * .15) + 1), 7, dtype=int)
    x_edges = np.linspace(int(w * .05), max(int(w * .95), int(w * .05) + 1), 9, dtype=int)
    gradient = cv2.magnitude(cv2.Sobel(light, cv2.CV_32F, 1, 0), cv2.Sobel(light, cv2.CV_32F, 0, 1))
    residual = np.abs(light.astype(np.float32) - cv2.medianBlur(light, 3).astype(np.float32))
    regions = []
    for row in range(6):
        for col in range(8):
            ys, xs = slice(y_edges[row], y_edges[row + 1]), slice(x_edges[col], x_edges[col + 1])
            tile = light[ys, xs]
            if not tile.size:
                continue
            p10, median, p90 = np.percentile(tile, [10, 50, 90])
            regions.append({
                "row": row, "col": col,
                "median": round(float(median), 2), "span": round(float(p90 - p10), 2),
                "p90": round(float(p90), 2),
                "edge_density": round(float(np.mean(gradient[ys, xs] > 40)), 4),
                "noise_proxy": round(float(np.median(residual[ys, xs]) / .6745), 2),
                "highlight_ratio": round(float(np.mean(tile >= 235)), 4),
            })
    return regions


def analyze_image(image):
    h, w = image.shape[:2]
    if min(h, w) < 4:
        raise ValueError("自动分析要求图片宽高至少为 4 像素")
    # Work on a bounded thumbnail so memory and feature scale remain predictable.
    scale = min(1.0, 800 / max(h, w))
    small = cv2.resize(image, (max(4, round(w * scale)), max(4, round(h * scale))),
                       interpolation=cv2.INTER_AREA)
    light = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)[:, :, 0]
    sh, sw = light.shape
    x0, x1 = int(sw * .05), max(int(sw * .95), int(sw * .05) + 4)
    y0, y1 = int(sh * .15), max(int(sh * .90), int(sh * .15) + 4)
    roi = light[y0:min(y1, sh), x0:min(x1, sw)]
    tiles = [tile for row in np.array_split(roi, 4)
             for tile in np.array_split(row, 4, axis=1) if tile.size]
    medians = np.array([np.median(tile) for tile in tiles])
    p10, p90 = np.percentile(roi, [10, 90])
    metrics = {
        "median_lightness": float(np.median(roi)),
        "p10_lightness": float(p10), "p90_lightness": float(p90),
        "dark_ratio": float(np.mean(roi < 50)),
        "highlight_ratio": float(np.mean(roi > 245)),
        "dark_tile_ratio": float(np.mean(medians < 125)),
        "tile_median_spread": float(np.percentile(medians, 90) - np.percentile(medians, 10)),
        "local_contrast": float(np.median([np.percentile(t, 90) - np.percentile(t, 10) for t in tiles])),
    }
    return {key: round(value, 4) for key, value in metrics.items()}


def select_plan(metrics, regions):
    """Select spatial tone curves from per-cell evidence; never sharpen/denoise."""
    category = "neutral"
    reason = "未达到持续偏暗或局部细节调整条件，采用中性处理以减少干扰。"
    gamma = 1.0
    globally_dark = False
    if (metrics["median_lightness"] < 125 and metrics["p90_lightness"] < 200
            and metrics["dark_tile_ratio"] >= .25):
        category, gamma = "dark", 1.18
        globally_dark = True
        reason = "参考区域中位亮度低于125、P90低于200，且至少25%的分块偏暗。"
    chosen = []
    shadow_cells, contrast_cells = 0, 0
    for region in regions:
        textured = .04 <= region["edge_density"] <= .65 and region["noise_proxy"] <= 6
        local_gamma, gain = 1.0, 1.0
        if (textured and region["median"] < 140 and region["p90"] < 215
                and region["span"] >= 35):
            local_gamma = round(1 + float(np.clip((145 - region["median"]) / 300, .04, .20)), 3)
        if globally_dark:
            local_gamma = max(local_gamma, 1.18)
        if (textured and 35 <= region["span"] < 95 and 80 < region["median"] < 205
                and region["highlight_ratio"] < .02):
            gain = round(1 + float(np.clip((100 - region["span"]) / 350, .02, .14)), 3)
        shadow_cells += local_gamma > 1
        contrast_cells += gain > 1
        chosen.append({**region, "gamma": local_gamma, "contrast_gain": gain})
    # A single atypical patch is weak evidence. Avoid routing a whole photograph on it.
    if not globally_dark and shadow_cells < 3:
        for region in chosen:
            region["gamma"] = 1.0
        shadow_cells = 0
    if contrast_cells < 3:
        for region in chosen:
            region["contrast_gain"] = 1.0
        contrast_cells = 0
    if not globally_dark:
        if shadow_cells and contrast_cells:
            category = "mixed"
        elif shadow_cells:
            category = "uneven"
        elif contrast_cells:
            category = "contrast"
        if category != "neutral":
            reason = f"48个参考分区中，{shadow_cells}个选择提亮、{contrast_cells}个选择对比增强；参数连续过渡。"
    if chosen:
        gamma = max(r["gamma"] for r in chosen)
    warnings = []
    if metrics["highlight_ratio"] >= .01:
        warnings.append("参考区域有较多高亮像素，可能来自白色包装或反光；本处理不恢复遮挡细节。")
    if metrics["local_contrast"] < 60:
        warnings.append("局部对比偏低；仅对有边缘线索的分区有限度拉伸，不代表已检测到文字。")
    return {
        "mode": "auto", "rule_version": RULE_VERSION,
        "category": category, "label": LABELS[category], "reason": reason,
        "analysis_region": {"type": "central_reference", "normalized_xyxy": [.05, .15, .95, .90],
                            "note": "固定中央参考区域，不是烟盒或柜台检测结果"},
        "metrics": metrics, "warnings": warnings,
        "regions": chosen,
        "region_summary": {"shadow_cells": shadow_cells, "contrast_cells": contrast_cells,
                           "grid_rows": 6, "grid_cols": 8},
        "selected_params": {"brightness": 0, "contrast": 1.0, "gamma": gamma,
                            "denoise": 0, "use_clahe": False, "reduce_overexpose": False,
                            "threshold": 250, "spatial_shadow_only": not globally_dark,
                            "local_contrast_gain_max": max((r["contrast_gain"] for r in chosen), default=1.0),
                            "max_lightness_lift": 18 if category != "neutral" else 0,
                            "max_lightness_drop": 6 if contrast_cells else 0,
                            "highlight_protection_start": 200, "highlight_protection_end": 235},
    }


def _parameter_maps(shape, plan):
    """Interpolate the parameters, not the image: no blur of text or hard tiles."""
    h, w = shape
    small_h, small_w = max(4, round(h * min(1, 600 / max(h, w)))), max(4, round(w * min(1, 600 / max(h, w))))
    x0, x1 = int(small_w * .05), max(int(small_w * .95), int(small_w * .05) + 1)
    y0, y1 = int(small_h * .15), max(int(small_h * .90), int(small_h * .15) + 1)
    grids = [np.zeros((6, 8), np.float32) for _ in range(3)]
    for region in plan["regions"]:
        pos = region["row"], region["col"]
        grids[0][pos] = region["gamma"] - 1
        grids[1][pos] = region["contrast_gain"] - 1
        grids[2][pos] = region["median"]
    maps = []
    for index, grid in enumerate(grids):
        canvas = np.full((small_h, small_w), 128 if index == 2 else 0, np.float32)
        canvas[y0:y1, x0:x1] = cv2.resize(grid, (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
        maps.append(cv2.GaussianBlur(canvas, (0, 0), sigmaX=max(1, min(small_h, small_w) / 80)))
    return maps


def apply_plan(image, plan):
    # LAB round-trip matches the existing D-style neutral baseline.
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    applied = {"max_lift": 0, "max_drop": 0, "changed_pixel_ratio": 0.0}
    if plan["category"] == "neutral":
        plan["applied_adjustment"] = applied
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    params = plan["selected_params"]
    maps = _parameter_maps(lab.shape[:2], plan)
    # Process stripes to bound extra memory for multi-megapixel originals.
    h, w = lab.shape[:2]
    mh, mw = maps[0].shape
    changed = 0
    map_x = np.broadcast_to(((np.arange(w, dtype=np.float32) + .5) * mw / w - .5)[None, :], (min(256, h), w)).copy()
    for y in range(0, h, 256):
        end = min(y + 256, h)
        map_y = np.broadcast_to(((np.arange(y, end, dtype=np.float32) + .5) * mh / h - .5)[:, None], (end - y, w)).copy()
        gamma_delta, gain_delta, pivot = [cv2.remap(m, map_x[:end-y], map_y, cv2.INTER_LINEAR,
                                                   borderMode=cv2.BORDER_REPLICATE) for m in maps]
        light = lab[y:end, :, 0].astype(np.float32)
        corrected = 255 * np.power(light / 255, 1 / (1 + gamma_delta))
        contrast_delta = np.clip((light - pivot) * gain_delta, -6, 6)
        delta = np.clip(corrected - light + contrast_delta,
                        -params["max_lightness_drop"], params["max_lightness_lift"])
        # No lift of near-black pixels, and no modification at L>=235.
        protection = np.clip((235 - light) / 35, 0, 1) * np.clip(light / 25, 0, 1)
        adjusted = np.clip(np.rint(light + delta * protection), 0, 255).astype(np.uint8)
        actual_delta = adjusted.astype(np.int16) - light.astype(np.int16)
        applied["max_lift"] = max(applied["max_lift"], int(actual_delta.max()))
        applied["max_drop"] = max(applied["max_drop"], int(-actual_delta.min()))
        changed += int(np.count_nonzero(actual_delta))
        lab[y:end, :, 0] = adjusted
    applied["changed_pixel_ratio"] = round(changed / (h * w), 4)
    plan["applied_adjustment"] = applied
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def auto_adjust(image):
    plan = select_plan(analyze_image(image), analyze_regions(image))
    return apply_plan(image, plan), plan
