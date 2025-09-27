# recommend.py
from models import dish_model, user_model

def score_dish(d: dish_model.Dish, prefs: user_model.UserPreferences) -> float:
    score = 0.0
    if prefs.favorite_tags:
        score += 3 * len(set(d.tags) & set(prefs.favorite_tags))
    if prefs.calorie_target and d.calories:
        diff = abs(d.calories - prefs.calorie_target)
        score += max(0, 10 - diff / 50)
    score += (hash(d.cuisine or "") % 5) * 0.1
    if prefs.avoid_spicy and d.is_spicy: score -= 5
    if prefs.vegan_only and not d.is_vegan: score -= 100
    if any(t in d.tags for t in prefs.dislikes): score -= 8
    return score
