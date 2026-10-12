#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦点餐参谋长 · 凑单优化引擎（meal_optimizer）

在「预算硬约束」下，从门店实时菜单中搜索最优餐品组合：
  - 多目标：口味偏好匹配 × 预算利用率 × 营养均衡（热量/蛋白质）
  - 输出 Top-K 套候选方案，供 AI 调用麦当劳 MCP 的 calculate-price 逐一核价

纯 Python 标准库实现，零第三方依赖。

用法：
  python3 meal_optimizer.py --menu menu.json --budget 60 --people 2 \
      --like spicy,chicken --avoid beef --max-kcal 800 --top 3

menu.json 由 AI 调用麦当劳 MCP 的 query-meals 工具后整理得到，格式：
{
  "items": [
    {"code": "M001", "name": "麦辣鸡腿汉堡", "price": 22.0, "category": "burger", "tags": ["spicy", "chicken"]}
  ]
}
category 取值：staple(主食/汉堡/卷) | snack(小食) | drink(饮料) | dessert(甜品) | combo(套餐)
price 单位自动识别：若中位数 > 200 视为「分」，自动除以 100 转为「元」。

可选营养库 --nutrition nutrition.json（由 list-nutrition-foods 整理）：
{"麦辣鸡腿汉堡": {"kcal": 485, "protein": 24}}
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from statistics import median

# ---------------------------------------------------------------------------
# 偏好词 → 餐品名称关键词映射（用于从名称推断标签）
# ---------------------------------------------------------------------------
PREFERENCE_KEYWORDS = {
    "spicy":   ["辣"],
    "beef":    ["牛", "安格斯", "巨无霸", "吉士"],
    "chicken": ["鸡"],
    "fish":    ["鱼", "鳕"],
    "pork":    ["猪"],
    "sweet":   ["新地", "麦旋风", "派", "冰淇淋", "圆筒", "雪冰", "阿芙佳朵"],
    "coffee":  ["咖啡", "美式", "奶铁", "玛奇朵", "卡布奇诺"],
    "tea":     ["红茶", "抹茶"],
    "breakfast": ["麦满分", "早安", "粥", "油条", "薯饼", "松饼"],
}

CATEGORY_ALIAS = {
    "burger": "staple", "汉堡": "staple", "主食": "staple", "卷": "staple",
    "小食": "snack", "小食拼盘": "snack",
    "饮料": "drink", "饮品": "drink", "咖啡": "drink",
    "甜品": "dessert", "冰淇淋": "dessert",
    "套餐": "combo",
}


@dataclass
class Item:
    code: str
    name: str
    price: float          # 元
    category: str         # staple/snack/drink/dessert/combo
    tags: set = field(default_factory=set)
    kcal: float = 0.0
    protein: float = 0.0

    def to_dict(self):
        return {
            "code": self.code, "name": self.name,
            "price": round(self.price, 2), "category": self.category,
            "kcal": self.kcal, "protein": self.protein,
        }


def infer_tags(name: str) -> set:
    """根据餐品名称推断口味标签。"""
    tags = set()
    for tag, keywords in PREFERENCE_KEYWORDS.items():
        if any(k in name for k in keywords):
            tags.add(tag)
    return tags


def load_menu(path: str, nutrition: dict | None = None) -> list[Item]:
    """加载菜单，做字段归一化、价格单位自动识别与标签推断。"""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    raw_items = raw.get("items", raw if isinstance(raw, list) else [])
    if not raw_items:
        sys.exit("菜单为空：请检查 menu.json 是否包含 items 数组")

    # 价格字段兼容 price / priceYuan / priceCent / salePrice
    def pick_price(d):
        for k in ("price", "priceYuan", "salePrice", "priceCent"):
            if d.get(k) is not None:
                return float(d[k])
        return None

    prices = [p for p in (pick_price(d) for d in raw_items) if p]
    unit_div = 100.0 if prices and median(prices) > 200 else 1.0  # 分 → 元

    items = []
    for d in raw_items:
        name = d.get("name") or d.get("productName") or ""
        price = pick_price(d)
        if not name or price is None:
            continue
        cat_raw = str(d.get("category") or d.get("categoryName") or "").strip()
        cat = CATEGORY_ALIAS.get(cat_raw, cat_raw if cat_raw in
                                 ("staple", "snack", "drink", "dessert", "combo") else "snack")
        tags = set(d.get("tags") or []) | infer_tags(name)
        nut = (nutrition or {}).get(name, {})
        items.append(Item(
            code=str(d.get("code") or d.get("productCode") or name),
            name=name,
            price=round(price / unit_div, 2),
            category=cat,
            tags=tags,
            kcal=float(nut.get("kcal", 0) or 0),
            protein=float(nut.get("protein", 0) or 0),
        ))
    return items


@dataclass
class Plan:
    """单人份方案；多人场景按人均预算求解后由调用方放大。"""
    items: list = field(default_factory=list)  # list[Item]
    total: float = 0.0
    kcal: float = 0.0
    protein: float = 0.0
    score: float = 0.0

    def to_dict(self):
        return {
            "items": [i.to_dict() for i in self.items],
            "totalPrice": round(self.total, 2),
            "totalKcal": round(self.kcal, 1),
            "totalProtein": round(self.protein, 1),
            "score": round(self.score, 2),
        }


def build_plan(combo: list[Item], likes: set, budget_pp: float,
               max_kcal: float, mode: str) -> Plan | None:
    """评估一个候选组合，返回打分后的 Plan；违反硬约束返回 None。"""
    total = sum(i.price for i in combo)
    if total > budget_pp + 1e-6:          # 预算硬约束
        return None
    # 忌口硬约束
    for i in combo:
        if i.tags & set(build_plan._avoid):
            return None
    kcal = sum(i.kcal for i in combo)
    if max_kcal and kcal > max_kcal:
        return None

    # ---- 多目标打分 ----
    pref_hits = sum(len(i.tags & likes) for i in combo)
    protein = sum(i.protein for i in combo)
    if mode == "saver":
        # 省钱模式：偏好优先，价格越低越好
        score = pref_hits * 10 - total * 1.0 + protein * 0.05
    else:
        # full 模式（默认）：吃满预算，预算利用率越高越好
        waste = budget_pp - total
        score = pref_hits * 10 - waste * 0.8 + protein * 0.05
    return Plan(items=list(combo), total=total, kcal=kcal,
                protein=protein, score=score)


def optimize(items: list[Item], budget: float, people: int,
             likes: set, avoid: set, max_kcal: float,
             top: int, mode: str, with_dessert: bool) -> list[Plan]:
    """
    以「人均预算」为约束枚举 主食×饮料×小食(×甜品) 组合，返回 Top-K 单人方案。
    套餐(combo) 视作独立主食参与枚举（其价格已含饮料小食）。
    """
    build_plan._avoid = avoid
    budget_pp = budget / max(people, 1)

    staples = [i for i in items if i.category in ("staple", "combo")]
    drinks  = [i for i in items if i.category == "drink"]
    snacks  = [i for i in items if i.category == "snack"]
    desserts = [i for i in items if i.category == "dessert"] if with_dessert else []

    if not staples:
        sys.exit("菜单中没有主食类餐品（category=staple/combo），无法组餐")

    none_item = None
    best: list[Plan] = []
    for s in staples:
        for d in ([none_item] + drinks if s.category == "staple" else [none_item]):
            for n in ([none_item] + snacks if s.category == "staple" else [none_item]):
                base = [x for x in (s, d, n) if x]
                # 主食+饮料+小食已超人均预算则跳过甜品枚举
                if sum(i.price for i in base) > budget_pp:
                    continue
                dessert_options = ([none_item] + desserts) if desserts else [none_item]
                for de in dessert_options:
                    combo = base + ([de] if de else [])
                    plan = build_plan(combo, likes, budget_pp, max_kcal, mode)
                    if plan is None:
                        continue
                    # 插入并保持 best 按分数降序、最多保留 top*4 条候选
                    best.append(plan)
    best.sort(key=lambda p: p.score, reverse=True)

    # 去重（相同餐品集合只留最高分）
    seen, results = set(), []
    for p in best:
        key = tuple(sorted(i.code for i in p.items))
        if key in seen:
            continue
        seen.add(key)
        results.append(p)
        if len(results) >= top:
            break
    return results


def pretty_print(plans: list[Plan], budget: float, people: int):
    """人类可读的方案对比输出。"""
    for idx, p in enumerate(plans, 1):
        line = " + ".join(f"{i.name}(¥{i.price:g})" for i in p.items)
        total_all = p.total * people
        print(f"\n【方案 {idx}】人均 ¥{p.total:.2f} × {people}人 = ¥{total_all:.2f}"
              f"（预算 ¥{budget:g}，剩余 ¥{budget - total_all:.2f}）")
        print(f"  组合：{line}")
        if p.kcal:
            print(f"  营养：约 {p.kcal:.0f} kcal / 蛋白质 {p.protein:.0f} g（人均）")


def main():
    ap = argparse.ArgumentParser(description="麦麦点餐参谋长 · 凑单优化引擎")
    ap.add_argument("--menu", required=True, help="菜单 JSON（query-meals 整理结果）")
    ap.add_argument("--budget", type=float, required=True, help="总预算（元）")
    ap.add_argument("--people", type=int, default=1, help="就餐人数，默认 1")
    ap.add_argument("--like", default="", help="偏好标签，逗号分隔，如 spicy,chicken")
    ap.add_argument("--avoid", default="", help="忌口标签，逗号分隔，如 beef")
    ap.add_argument("--max-kcal", type=float, default=0, help="人均热量上限 kcal，0 为不限制")
    ap.add_argument("--top", type=int, default=3, help="输出方案数，默认 3")
    ap.add_argument("--mode", choices=["full", "saver"], default="full",
                    help="full=吃满预算更丰盛（默认）| saver=能省则省")
    ap.add_argument("--with-dessert", action="store_true", help="允许甜品进入组合")
    ap.add_argument("--nutrition", default="", help="营养库 JSON（可选）")
    ap.add_argument("--json", action="store_true", help="仅输出 JSON（供程序消费）")
    args = ap.parse_args()

    nutrition = None
    if args.nutrition:
        with open(args.nutrition, encoding="utf-8") as f:
            nutrition = json.load(f)

    items = load_menu(args.menu, nutrition)
    likes = {t.strip() for t in args.like.split(",") if t.strip()}
    avoid = {t.strip() for t in args.avoid.split(",") if t.strip()}

    plans = optimize(items, args.budget, args.people, likes, avoid,
                     args.max_kcal, args.top, args.mode, args.with_dessert)

    if args.json:
        print(json.dumps({
            "budget": args.budget, "people": args.people,
            "budgetPerPerson": round(args.budget / max(args.people, 1), 2),
            "plans": [p.to_dict() for p in plans],
        }, ensure_ascii=False, indent=2))
    else:
        if not plans:
            print("没有找到满足约束的组合：请提高预算、放宽忌口或热量限制。")
            return
        pretty_print(plans, args.budget, args.people)
        print("\n下一步：把候选方案的 productCode 列表交给 MCP calculate-price 逐一核价，"
              "叠加优惠券后选出实付最低的一套。")


if __name__ == "__main__":
    main()
