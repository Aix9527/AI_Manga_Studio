"""Chinese emotion/action keyword mapper — provides structured mappings
for Director and Vision modules to consume.

Covers:
- Emotion keywords → intensity + visual suggestions
- Action verbs → shot type recommendations
- Atmosphere descriptors → color palette hints
"""

from __future__ import annotations


class EmotionMapper:
    """Maps Chinese emotion/action keywords to structured visual directives."""

    # Emotion → (intensity 0-10, visual prompt hint, color suggestion)
    EMOTION_MAP: dict[str, tuple[int, str, str]] = {
        # Anger spectrum
        "愤怒": (8, "clenched fists, furrowed brows, tense posture", "red-black"),
        "狂怒": (10, "explosive rage, veins bulging, eyes blazing", "crimson-dark"),
        "怒气": (7, "suppressed anger, tense jaw, narrowed eyes", "dark-red"),
        "恼怒": (5, "irritated frown, impatient gesture", "warm-orange"),
        # Fear spectrum
        "恐惧": (8, "trembling, wide eyes, shallow breathing", "cold-gray"),
        "害怕": (6, "flinching, defensive posture, rapid heartbeat", "pale-blue"),
        "惊恐": (9, "frozen in terror, pupils dilated", "sharp-white"),
        "畏惧": (5, "hesitation, avoiding eye contact", "muted-purple"),
        # Sadness spectrum
        "悲伤": (7, "tears streaming, bowed head, trembling lips", "blue-gray"),
        "痛苦": (8, "agonized expression, clutching chest", "deep-purple"),
        "绝望": (10, "hollow eyes, lifeless posture, void expression", "black-white"),
        "哀伤": (6, "melancholy gaze, slow movements", "soft-blue"),
        "凄凉": (5, "lonely silhouette, desolate atmosphere", "gray-blue"),
        "心碎": (9, "heartbreaking sobbing, collapsed posture", "dark-violet"),
        # Joy spectrum
        "喜悦": (6, "bright smile, sparkling eyes, relaxed posture", "warm-golden"),
        "兴奋": (7, "animated gestures, flushed cheeks, rapid speech", "bright-yellow"),
        "惊喜": (8, "eyes widening in delight, gasp, open posture", "golden-pink"),
        "欣慰": (5, "gentle smile, soft eyes, relaxed shoulders", "warm-amber"),
        # Calm spectrum
        "冷静": (3, "steady gaze, controlled breathing, composed", "cool-blue"),
        "冰冷": (4, "icy stare, emotionless expression, rigid posture", "ice-blue"),
        "淡漠": (2, "indifferent eyes, minimal expression, distant", "gray-white"),
        "平静": (1, "serene face, slow breath, still posture", "soft-green"),
        # Tender spectrum
        "温柔": (4, "soft gaze, gentle touch, warm smile", "pink-golden"),
        "深情": (6, "intense gaze, intimate proximity, flushed", "rose-red"),
        "心动": (7, "racing heart, shy glance, blushing", "cherry-pink"),
        # Tension spectrum
        "紧张": (5, "sweating, rapid heartbeat, alert posture", "orange-yellow"),
        "焦虑": (6, "pacing, nail biting, restless eyes", "muted-orange"),
        # Resolve spectrum
        "坚定": (5, "steady gaze, clenched fist, upright posture", "steel-blue"),
        "决然": (7, "decisive movement, unwavering eyes, forward lean", "iron-gray"),
        # Loneliness spectrum
        "孤独": (5, "solitary figure, distant gaze, empty surroundings", "mono-blue"),
        "寂寞": (4, "quiet stillness, wistful expression", "pale-purple"),
        # Longing spectrum
        "思念": (5, "distant gaze, gentle sigh, reaching hand", "moon-white"),
        "怀念": (4, "nostalgic smile, old photograph, warm memory", "sepia-gold"),
    }

    # Action → (intensity, shot_type_suggestion, visual_focus)
    ACTION_MAP: dict[str, tuple[int, str, str]] = {
        "拔剑": (7, "close-up", "hand on hilt, blade emerging, metallic glint"),
        "握拳": (5, "close-up", "knuckles whitening, tension in forearm"),
        "流泪": (6, "close-up", "teardrop tracing cheek, trembling lashes"),
        "微笑": (3, "medium", "gentle curve of lips, soft eye corners"),
        "苦笑": (4, "close-up", "bittersweet half-smile, tired eyes"),
        "冷笑": (5, "close-up", "cold smirk, sharp side-glance"),
        "怒吼": (8, "medium", "mouth wide, throat strained, voice visible"),
        "冲锋": (8, "wide→close-up tracking", "forward momentum, dust kicking up"),
        "跃起": (7, "low-angle", "figure rising against sky, cape flowing"),
        "转身": (3, "medium", "body rotating, hair swinging, clothing shift"),
        "凝视": (4, "close-up", "unblinking eyes, reflected light in pupils"),
        "施法": (7, "wide", "glowing hands, energy swirling, runes appearing"),
        "召唤": (8, "wide", "portal opening, light bursting, figure emerging"),
        "封印": (9, "panorama→close-up", "sealing array expanding, energy compressing"),
        "星纹": (6, "extreme-close-up", "glowing tattoo/cracks on skin, pulsing light"),
        "觉醒": (8, "low-angle+close-up", "power erupting, eyes glowing, hair rising"),
    }

    # Atmosphere → (visual_tone, lighting, dominant_color)
    ATMOSPHERE_MAP: dict[str, tuple[str, str, str]] = {
        "悲壮": ("tragic heroic", "dramatic backlight, deep shadows", "crimson-black"),
        "温馨": ("warm intimate", "soft amber light, gentle shadows", "warm-golden"),
        "肃杀": ("deadly serious", "harsh overhead light, sharp shadows", "steel-gray"),
        "神秘": ("mysterious", "fog-filtered light, long shadows", "purple-blue"),
        "恐怖": ("horror", "undercast light, extreme shadows", "red-black"),
        "悠然": ("peaceful", "golden hour, soft diffuse light", "warm-yellow"),
        "壮阔": ("epic scale", "god rays, dramatic clouds", "golden-blue"),
        "压抑": ("oppressive", "overcast, muted colors, heavy shadows", "gray-blue"),
        "浪漫": ("romantic", "candlelight, cherry blossoms, bokeh", "pink-golden"),
        "荒凉": ("desolate", "harsh sun, long shadows, dust", "brown-yellow"),
    }

    def map_emotion(self, keyword: str) -> dict | None:
        """Map a Chinese emotion keyword to visual directives."""
        if keyword in self.EMOTION_MAP:
            intensity, visual_hint, color = self.EMOTION_MAP[keyword]
            return {
                "keyword": keyword,
                "intensity": intensity,
                "visual_hint": visual_hint,
                "color_palette": color,
            }
        return None

    def map_action(self, keyword: str) -> dict | None:
        """Map a Chinese action verb to shot directives."""
        if keyword in self.ACTION_MAP:
            intensity, shot_type, visual_focus = self.ACTION_MAP[keyword]
            return {
                "keyword": keyword,
                "intensity": intensity,
                "shot_type": shot_type,
                "visual_focus": visual_focus,
            }
        return None

    def map_atmosphere(self, keyword: str) -> dict | None:
        """Map a Chinese atmosphere descriptor."""
        if keyword in self.ATMOSPHERE_MAP:
            tone, lighting, color = self.ATMOSPHERE_MAP[keyword]
            return {
                "keyword": keyword,
                "visual_tone": tone,
                "lighting": lighting,
                "dominant_color": color,
            }
        return None

    def analyze_text(self, text: str) -> dict:
        """Analyze a Chinese text block and return all detected mappings."""
        result = {
            "emotions": [],
            "actions": [],
            "atmospheres": [],
        }

        for keyword in self.EMOTION_MAP:
            if keyword in text:
                mapped = self.map_emotion(keyword)
                if mapped:
                    result["emotions"].append(mapped)

        for keyword in self.ACTION_MAP:
            if keyword in text:
                mapped = self.map_action(keyword)
                if mapped:
                    result["actions"].append(mapped)

        for keyword in self.ATMOSPHERE_MAP:
            if keyword in text:
                mapped = self.map_atmosphere(keyword)
                if mapped:
                    result["atmospheres"].append(mapped)

        return result

    def get_shot_prompt_hints(self, text: str) -> list[str]:
        """Generate visual prompt hints from detected emotions/actions."""
        hints = []
        analysis = self.analyze_text(text)

        for emo in analysis["emotions"]:
            hints.append(f"({emo['keyword']}:{emo['visual_hint']}, palette={emo['color_palette']})")

        for act in analysis["actions"]:
            hints.append(f"(action:{act['keyword']} → {act['shot_type']}, focus:{act['visual_focus']})")

        return hints
