# models/recommendation_engine.py
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from bson import ObjectId
import math

class DishRecommendationEngine:
    """
    Optimized Hybrid Recommendation Engine:
    - Personalized: High rating + User preferences + Time habits + Ingredient analysis
    - Trending: High average_rating (sorted DESC)
    """

    def __init__(self, db):
        self.db = db
        # Adjusted weights for high-rating priority
        self.weights = {
            "rating_quality": 0.30,      # Ưu tiên món rating cao
            "collaborative": 0.25,        # Users tương tự
            "ingredient_match": 0.20,     # Khớp nguyên liệu yêu thích
            "time_habit": 0.10,          # Thói quen thời gian
            "popularity": 0.10,           # Like/cook count
            "recency": 0.05,              # Món mới
        }
        
        # Time ranges for meal detection
        self.meal_times = {
            "breakfast": (6, 10),
            "lunch": (10, 14),
            "dinner": (17, 21),
            "late_night": (21, 24),
        }

    # ===== PUBLIC API =====

    async def get_recommendations(
        self,
        user_id: ObjectId,
        limit: int = 20,
        exclude_seen: bool = True,
        min_rating: float = 3.5,  # Chỉ recommend món >= 3.5 sao
    ) -> List[Dict]:
        """
        Personalized recommendations dựa trên:
        - High rating dishes (min_rating)
        - User preferences & ingredient habits
        - Time-based patterns
        - Collaborative filtering
        """
        # Load user data
        user_activity = await self.db.user_activity.find_one({"user_id": user_id}) or {}
        user_prefs = await self.db.user_preferences.find_one({"user_id": user_id}) or {}

        # Fallback for new users
        if not user_activity or not user_activity.get("viewed_dishes_and_users"):
            return await self.get_popular_dishes(limit, user_prefs, min_rating=min_rating)

        # Extract user patterns
        user_patterns = self._analyze_user_patterns(user_activity)

        # Build query
        match_query = {
            "is_active": True,
            "average_rating": {"$gte": min_rating},  # ✅ Ưu tiên món rating cao
        }
        
        # Apply user preferences
        if user_prefs.get("cuisine_preferences"):
            match_query["cuisine_type"] = {"$in": user_prefs["cuisine_preferences"]}
        if user_prefs.get("difficulty_preference") and user_prefs["difficulty_preference"] != "all":
            match_query["difficulty"] = user_prefs["difficulty_preference"]

        # Get candidate dishes
        all_dishes = await self.db.dishes.find(match_query).to_list(length=None)

        # Exclude seen dishes
        if exclude_seen:
            seen_ids = self._get_seen_dish_ids(user_activity)
            all_dishes = [d for d in all_dishes if str(d["_id"]) not in seen_ids]

        if not all_dishes:
            return await self.get_popular_dishes(limit, user_prefs, min_rating=min_rating)

        # Find similar users (cached)
        similar_users = await self._find_similar_users(
            user_id, 
            set(str(x) for x in user_activity.get("favorite_dishes", []))
        )

        # Batch load similar users' activities
        sim_activities_map = await self._load_similar_activities(similar_users)

        # Score all dishes
        scored = []
        for dish in all_dishes:
            score_breakdown = await self._calculate_personalized_score(
                dish, user_activity, user_prefs, user_patterns,
                similar_users, sim_activities_map
            )
            scored.append({
                "dish": dish,
                "score": score_breakdown["total"],
                "breakdown": score_breakdown
            })

        # Sort by score
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Diversify results
        diverse = self._diversify_results(scored, limit)
        return diverse[:limit]

    async def get_trending_dishes(
        self, 
        days: int = 7, 
        limit: int = 20,
        min_rating: float = 4.0,  # Trending phải >= 4 sao
        min_ratings_count: int = 5  # Tối thiểu 5 ratings
    ) -> List[Dict]:
        """
        Trending dishes: Món có rating cao + nhiều tương tác gần đây
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        # Query: High rating + enough ratings + active
        match_query = {
            "is_active": True,
            "average_rating": {"$gte": min_rating},
            "ratings": {"$exists": True, "$not": {"$size": 0}}  # Có ratings
        }
        
        dishes = await self.db.dishes.find(match_query).to_list(length=None)
        
        # Filter dishes with enough ratings
        valid_dishes = [
            d for d in dishes 
            if len(d.get("ratings", [])) >= min_ratings_count
        ]

        # Calculate trending score
        def trending_score(dish: Dict) -> float:
            rating = dish.get("average_rating", 0)
            likes = dish.get("like_count", 0)
            cooks = dish.get("cook_count", 0)
            views = dish.get("view_count", 0)
            
            # Rating weight cao nhất
            rating_score = rating * 20  # Rating 5 sao = 100 points
            
            # Engagement score
            engagement = likes * 3 + cooks * 2 + views * 0.5
            engagement_score = math.log1p(engagement) * 5
            
            # Recency boost
            created = dish.get("created_at")
            recency_boost = 1.0
            if isinstance(created, datetime):
                age_days = (datetime.utcnow() - created).days
                if age_days <= days:
                    recency_boost = 1.5  # Boost 50% nếu mới
            
            return (rating_score + engagement_score) * recency_boost

        valid_dishes.sort(key=trending_score, reverse=True)
        return valid_dishes[:limit]

    async def get_popular_dishes(
        self, 
        limit: int, 
        user_prefs: Optional[Dict] = None,
        min_rating: float = 3.5
    ) -> List[Dict]:
        """
        Popular dishes for new users (fallback)
        """
        query = {
            "is_active": True,
            "average_rating": {"$gte": min_rating}
        }
        
        # Apply dietary restrictions
        if user_prefs and user_prefs.get("dietary_restrictions"):
            query["tags"] = {"$nin": [r.lower() for r in user_prefs["dietary_restrictions"]]}

        dishes = await (
            self.db.dishes.find(query)
            .sort([
                ("average_rating", -1),
                ("like_count", -1),
                ("cook_count", -1)
            ])
            .limit(limit)
            .to_list(limit)
        )
        
        return [
            {
                "dish": d,
                "score": d.get("average_rating", 0) / 5.0,
                "breakdown": {"popular": 1.0, "total": d.get("average_rating", 0) / 5.0}
            }
            for d in dishes
        ]

    async def get_similar_dishes(self, dish_id: str, limit: int = 10) -> List[Dict]:
        """Similar dishes based on content"""
        oid = _safe_oid(dish_id)
        if not oid:
            return []
        
        dish = await self.db.dishes.find_one({"_id": oid})
        if not dish:
            return []

        # Find similar by category, tags, cuisine, ingredients
        query = {
            "_id": {"$ne": oid},
            "is_active": True,
            "$or": [
                {"category": dish.get("category")},
                {"tags": {"$in": dish.get("tags", [])}},
                {"cuisine_type": dish.get("cuisine_type")},
                {"ingredients.name": {"$in": [ing.get("name") for ing in dish.get("ingredients", [])][:5]}}
            ]
        }
        
        similar = await (
            self.db.dishes.find(query)
            .sort([("average_rating", -1), ("like_count", -1)])
            .limit(limit)
            .to_list(limit)
        )
        
        return similar

    async def update_user_interaction(
        self, 
        user_id: ObjectId, 
        dish_id: str, 
        interaction_type: str
    ):
        """Track user interactions"""
        oid = _safe_oid(dish_id)
        if not oid:
            return

        # Get dish info for viewed_dishes_and_users format
        dish = await self.db.dishes.find_one({"_id": oid})
        if not dish:
            return

        now = datetime.utcnow()

        # Update user_activity based on interaction type
        if interaction_type == "view":
            view_entry = {
                "type": "dish",
                "id": str(oid),
                "name": dish.get("name", ""),
                "image": dish.get("image_url", ""),
                "ts": now
            }
            await self.db.user_activity.update_one(
                {"user_id": user_id},
                {
                    "$push": {"viewed_dishes_and_users": view_entry},
                    "$addToSet": {"viewed_dishes": str(oid)},
                    "$set": {"updated_at": now}
                },
                upsert=True
            )
            # Increment view count
            await self.db.dishes.update_one({"_id": oid}, {"$inc": {"view_count": 1}})

        elif interaction_type in ("favorite", "like"):
            await self.db.user_activity.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"favorite_dishes": str(oid)},
                    "$set": {"updated_at": now}
                },
                upsert=True
            )
            await self.db.dishes.update_one({"_id": oid}, {"$inc": {"like_count": 1}})

        elif interaction_type == "cook":
            await self.db.user_activity.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"cooked_dishes": str(oid)},
                    "$set": {"updated_at": now}
                },
                upsert=True
            )
            await self.db.dishes.update_one({"_id": oid}, {"$inc": {"cook_count": 1}})

    # ===== INTERNAL SCORING =====

    async def _calculate_personalized_score(
        self,
        dish: Dict,
        user_activity: Dict,
        user_prefs: Dict,
        user_patterns: Dict,
        similar_users: List[Tuple[ObjectId, float]],
        sim_activities_map: Dict[str, Dict]
    ) -> Dict[str, float]:
        """Calculate comprehensive personalized score"""
        scores = {}

        # 1. Rating Quality Score (30%)
        scores["rating_quality"] = self._rating_quality_score(dish)

        # 2. Collaborative Filtering (25%)
        scores["collaborative"] = self._collaborative_score_cached(
            dish, similar_users, sim_activities_map
        )

        # 3. Ingredient Match (20%)
        scores["ingredient_match"] = await self._ingredient_match_score(
            dish, user_patterns.get("favorite_ingredients", {})
        )

        # 4. Time Habit Score (10%)
        scores["time_habit"] = self._time_habit_score(
            dish, user_patterns.get("time_preferences", {})
        )

        # 5. Popularity (10%)
        scores["popularity"] = self._popularity_score(dish)

        # 6. Recency (5%)
        scores["recency"] = self._recency_score(dish)

        # Calculate weighted total
        total = sum(scores[k] * self.weights[k] for k in self.weights)
        scores["total"] = float(total)
        
        return scores

    def _rating_quality_score(self, dish: Dict) -> float:
        """
        Score based on average_rating
        5 sao = 1.0, 4 sao = 0.8, 3 sao = 0.6, etc.
        """
        rating = dish.get("average_rating", 0)
        ratings_count = len(dish.get("ratings", []))
        
        # Confidence factor (more ratings = more reliable)
        confidence = min(ratings_count / 10.0, 1.0)  # Max confidence at 10+ ratings
        
        # Normalize rating to 0-1
        normalized = rating / 5.0
        
        return normalized * (0.5 + 0.5 * confidence)  # Blend with confidence

    def _collaborative_score_cached(
        self,
        dish: Dict,
        similar_users: List[Tuple[ObjectId, float]],
        sim_activities_map: Dict[str, Dict]
    ) -> float:
        """Collaborative filtering based on similar users"""
        if not similar_users:
            return 0.5

        dish_id = str(dish["_id"])
        weighted_sum, total_weight = 0.0, 0.0

        for user_oid, similarity in similar_users[:20]:
            activity = sim_activities_map.get(str(user_oid))
            if not activity:
                continue

            favorites = set(activity.get("favorite_dishes", []))
            cooked = set(activity.get("cooked_dishes", []))

            # Weight: favorite = 1.0, cooked = 0.7
            if dish_id in favorites:
                weighted_sum += similarity * 1.0
            elif dish_id in cooked:
                weighted_sum += similarity * 0.7

            total_weight += similarity

        return min(weighted_sum / total_weight, 1.0) if total_weight > 0 else 0.5

    async def _ingredient_match_score(
        self, 
        dish: Dict, 
        favorite_ingredients: Dict[str, int]
    ) -> float:
        """
        Score based on matching favorite ingredients
        Phân tích: gà, hải sản, thịt bò, etc.
        """
        if not favorite_ingredients:
            return 0.5

        dish_ingredients = dish.get("ingredients", [])
        if not dish_ingredients:
            return 0.3

        # Extract ingredient names
        dish_ing_names = [
            ing.get("name", "").lower() 
            for ing in dish_ingredients
        ]

        # Calculate match ratio
        matches = 0
        total_weight = sum(favorite_ingredients.values())

        for fav_ing, weight in favorite_ingredients.items():
            # Check if any dish ingredient contains this favorite
            if any(fav_ing.lower() in d_ing for d_ing in dish_ing_names):
                matches += weight

        return min(matches / total_weight, 1.0) if total_weight > 0 else 0.5

    def _time_habit_score(self, dish: Dict, time_preferences: Dict[str, int]) -> float:
        """
        Score based on user's time habits
        Ví dụ: User hay nấu dinner -> ưu tiên món phù hợp dinner
        """
        if not time_preferences:
            return 0.5

        # Map cooking time to meal types
        cooking_time = dish.get("cooking_time", 30)
        
        # Heuristic: Quick dishes (< 30min) = breakfast/lunch
        # Long dishes (> 60min) = dinner
        if cooking_time < 30:
            meal_fit = ["breakfast", "lunch"]
        elif cooking_time < 60:
            meal_fit = ["lunch", "dinner"]
        else:
            meal_fit = ["dinner"]

        # Calculate match with user's most frequent time
        total_views = sum(time_preferences.values())
        match_score = sum(
            time_preferences.get(meal, 0) 
            for meal in meal_fit
        )

        return min(match_score / total_views, 1.0) if total_views > 0 else 0.5

    def _popularity_score(self, dish: Dict) -> float:
        """Popularity based on likes/cooks/views"""
        likes = dish.get("like_count", 0)
        cooks = dish.get("cook_count", 0)
        views = dish.get("view_count", 0)
        
        # Weighted popularity
        base = likes * 3 + cooks * 2 + views * 0.5
        
        return min(math.log1p(base) / math.log1p(5000), 1.0)

    def _recency_score(self, dish: Dict) -> float:
        """Boost for recently created dishes"""
        created = dish.get("created_at")
        if not isinstance(created, datetime):
            return 0.5

        days_old = (datetime.utcnow() - created).days
        
        if days_old <= 7:
            return 1.0
        elif days_old <= 30:
            return 0.8
        elif days_old <= 90:
            return 0.6
        else:
            return 0.4

    # ===== USER PATTERN ANALYSIS =====

    def _analyze_user_patterns(self, user_activity: Dict) -> Dict:
        """
        Analyze user patterns from history:
        - Favorite ingredients (gà, hải sản, thịt bò...)
        - Time preferences (breakfast, lunch, dinner)
        - Category preferences
        """
        patterns = {
            "favorite_ingredients": {},
            "time_preferences": {},
            "category_preferences": {}
        }

        # Analyze viewed dishes with timestamps
        viewed_history = user_activity.get("viewed_dishes_and_users", [])
        
        if not viewed_history:
            return patterns

        # Extract time preferences
        time_counts = defaultdict(int)
        for entry in viewed_history:
            if entry.get("type") != "dish":
                continue
            
            ts = entry.get("ts")
            if isinstance(ts, datetime):
                hour = ts.hour
                meal_type = self._detect_meal_type(hour)
                time_counts[meal_type] += 1

        patterns["time_preferences"] = dict(time_counts)

        # Note: Ingredient analysis requires loading dish details
        # This is expensive, so we do it lazily or cache it
        # For now, we'll mark it as TODO and implement if needed

        return patterns

    def _detect_meal_type(self, hour: int) -> str:
        """Detect meal type from hour"""
        for meal, (start, end) in self.meal_times.items():
            if start <= hour < end:
                return meal
        return "other"

    def _get_seen_dish_ids(self, user_activity: Dict) -> set:
        """Get all seen dish IDs"""
        seen = set()
        
        # From arrays
        for field in ["favorite_dishes", "cooked_dishes", "viewed_dishes"]:
            seen.update(str(x) for x in user_activity.get(field, []))
        
        # From viewed_dishes_and_users
        for entry in user_activity.get("viewed_dishes_and_users", []):
            if entry.get("type") == "dish":
                seen.add(entry.get("id"))
        
        return seen

    async def _find_similar_users(
        self, 
        user_id: ObjectId, 
        user_favorites: set
    ) -> List[Tuple[ObjectId, float]]:
        """Find users with similar taste (Jaccard similarity)"""
        if not user_favorites:
            return []

        cursor = self.db.user_activity.find({
            "user_id": {"$ne": user_id},
            "favorite_dishes": {"$exists": True, "$not": {"$size": 0}}
        })

        similarities = []
        async for activity in cursor:
            other_favorites = set(activity.get("favorite_dishes", []))
            if not other_favorites:
                continue

            # Jaccard similarity
            intersection = len(user_favorites & other_favorites)
            union = len(user_favorites | other_favorites)
            
            if union == 0:
                continue

            similarity = intersection / union
            
            if similarity > 0.1:  # Threshold
                similarities.append((activity["user_id"], similarity))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:50]  # Top 50 similar users

    async def _load_similar_activities(
        self, 
        similar_users: List[Tuple[ObjectId, float]]
    ) -> Dict[str, Dict]:
        """Batch load activities of similar users"""
        if not similar_users:
            return {}

        user_ids = [uid for uid, _ in similar_users]
        cursor = self.db.user_activity.find({"user_id": {"$in": user_ids}})
        
        activities_map = {}
        async for activity in cursor:
            activities_map[str(activity["user_id"])] = activity
        
        return activities_map

    def _diversify_results(self, scored: List[Dict], limit: int) -> List[Dict]:
        """Ensure diversity in results by category"""
        if not scored:
            return []

        result = []
        category_counts = defaultdict(int)
        max_per_category = max(3, limit // 5)  # Max 3 items per category

        # First pass: diversify
        for item in scored:
            category = item["dish"].get("category", "other").lower()
            
            if category_counts[category] < max_per_category:
                result.append(item)
                category_counts[category] += 1
            
            if len(result) >= limit:
                break

        # Second pass: fill remaining slots
        if len(result) < limit:
            for item in scored:
                if item not in result:
                    result.append(item)
                    if len(result) >= limit:
                        break

        return result

# ===== HELPER FUNCTIONS =====

def _safe_oid(value: str) -> Optional[ObjectId]:
    """Safely convert string to ObjectId"""
    try:
        return ObjectId(value)
    except Exception:
        return None