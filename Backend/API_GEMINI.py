import os
import unicodedata
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from google import genai

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Ingredient:
    """Model cho nguyên liệu"""
    id: str
    name: str
    normalized_name: str
    category: str
    unit: str = "gram"
    available_quantity: Optional[float] = None
    expiry_date: Optional[str] = None

@dataclass
class Recipe:
    """Model cho công thức nấu ăn"""
    id: str
    name: str
    description: str
    prep_time: int
    cook_time: int
    total_time: int
    servings: int
    difficulty: str
    cuisine_type: str
    ingredients_needed: List[Dict[str, Any]]
    instructions: List[str]
    nutrition: Optional[Dict[str, Any]] = None
    tags: List[str] = None
    image_url: Optional[str] = None
    match_score: float = 0.0

@dataclass
class RecipeSearchResult:
    """Kết quả tìm kiếm công thức"""
    recipes: List[Recipe]
    total_found: int
    search_time: float
    suggestions: List[str] = None

@dataclass
class IngredientSuggestion:
    """Gợi ý nguyên liệu"""
    id: str
    name: str
    category: str
    confidence: float
    related_recipes_count: int = 0
    commonly_paired_with: List[str] = None

# ============================================================================
# AI COOKING SERVICE
# ============================================================================

class AICookingService:
    def __init__(self, api_key: str):
        """Khởi tạo service với Gemini API key"""
        self.client = genai.Client(api_key=api_key)
        self.ingredient_categories = {
            "protein": ["thịt", "cá", "tôm", "cua", "gà", "vịt", "trứng", "đậu phụ"],
            "vegetables": ["rau", "củ", "quả", "nấm", "giá đỗ", "cà chua"],
            "grains": ["gạo", "bún", "miến", "bánh", "mì"],
            "seasonings": ["muối", "đường", "nước mắm", "tương ớt", "gia vị"],
            "dairy": ["sữa", "bơ", "phô mai", "yogurt"],
            "herbs": ["húng", "ngò", "kinh giới", "lá"]
        }
    
    def normalize_text(self, text: str) -> str:
        """Chuẩn hóa text tiếng Việt"""
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
    
    def categorize_ingredient(self, ingredient_name: str) -> str:
        """Phân loại nguyên liệu"""
        normalized_name = self.normalize_text(ingredient_name)
        
        for category, keywords in self.ingredient_categories.items():
            for keyword in keywords:
                if self.normalize_text(keyword) in normalized_name:
                    return category
        
        return "other"
    
    def correct_ingredient_name(self, raw_input: str) -> str:
        """Sửa chính tả tên nguyên liệu"""
        try:
            name_slug = self.normalize_text(raw_input)
            
            prompt = f"""Bạn là chuyên gia ẩm thực Việt Nam. Sửa chính tả nguyên liệu: "{name_slug}"
Chỉ trả về tên đã sửa, không giải thích.
Ví dụ: "ca chua" → "cà chua" """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt
            )
            
            return response.text.strip() if response.text else raw_input
            
        except Exception:
            return raw_input
    
    def suggest_ingredients(self, query: str, limit: int = 10) -> List[IngredientSuggestion]:
        """Gợi ý nguyên liệu dựa trên query"""
        try:
            prompt = f"""Gợi ý {limit} nguyên liệu liên quan đến "{query}".
Trả về danh sách tên nguyên liệu, mỗi tên một dòng.
Ví dụ:
thịt bò
thịt heo  
thịt gà"""
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt
            )
            
            if response.text:
                lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
                suggestions = []
                
                for i, name in enumerate(lines[:limit]):
                    suggestion = IngredientSuggestion(
                        id=f"ing_{i}_{hash(name)}",
                        name=name,
                        category=self.categorize_ingredient(name),
                        confidence=0.8,
                        commonly_paired_with=[]
                    )
                    suggestions.append(suggestion)
                
                return suggestions
            
            return []
            
        except Exception:
            return []
    
    def search_recipes_by_ingredients(self, 
                                    ingredients: List[str], 
                                    max_results: int = 10,
                                    difficulty: Optional[str] = None,
                                    max_cook_time: Optional[int] = None) -> RecipeSearchResult:
        """Tìm kiếm công thức dựa trên nguyên liệu"""
        start_time = datetime.now()
        
        try:
            # Sửa chính tả nguyên liệu
            corrected_ingredients = [self.correct_ingredient_name(ing) for ing in ingredients]
            
            # Tạo filter text
            filters = []
            if difficulty:
                filters.append(f"độ khó {difficulty}")
            if max_cook_time:
                filters.append(f"thời gian nấu tối đa {max_cook_time} phút")
            
            filter_text = f" ({', '.join(filters)})" if filters else ""
            
            prompt = f"""Từ nguyên liệu: {', '.join(corrected_ingredients)}
Gợi ý {max_results} món ăn Việt Nam{filter_text}.
Mỗi món một dòng, định dạng: Tên món - Thời gian chuẩn bị: X phút - Thời gian nấu: Y phút - Khẩu phần: Z người
Ví dụ:
Bò xào cà chua - Thời gian chuẩn bị: 10 phút - Thời gian nấu: 15 phút - Khẩu phần: 4 người
Canh chua cá - Thời gian chuẩn bị: 15 phút - Thời gian nấu: 20 phút - Khẩu phần: 3 người"""
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt
            )
            
            recipes = []
            
            if response.text:
                lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
                
                for i, line in enumerate(lines[:max_results]):
                    # Parse thông tin từ line
                    parts = line.split(' - ')
                    name = parts[0].strip()
                    
                    prep_time = 10
                    cook_time = 20
                    servings = 2
                    
                    # Extract thông tin nếu có
                    for part in parts[1:]:
                        if "chuẩn bị:" in part:
                            try:
                                prep_time = int(''.join(filter(str.isdigit, part)))
                            except:
                                pass
                        elif "nấu:" in part:
                            try:
                                cook_time = int(''.join(filter(str.isdigit, part)))
                            except:
                                pass
                        elif "phần:" in part:
                            try:
                                servings = int(''.join(filter(str.isdigit, part)))
                            except:
                                pass
                    
                    recipe = Recipe(
                        id=f"recipe_{i}_{hash(name)}",
                        name=name,
                        description=f"Món {name} được chế biến từ {', '.join(corrected_ingredients[:3])}",
                        prep_time=prep_time,
                        cook_time=cook_time,
                        total_time=prep_time + cook_time,
                        servings=servings,
                        difficulty=difficulty or "medium",
                        cuisine_type="vietnamese",
                        ingredients_needed=[{"name": ing, "quantity": "vừa đủ", "unit": "gram"} for ing in corrected_ingredients],
                        instructions=[f"Bước 1: Chuẩn bị {', '.join(corrected_ingredients)}", f"Bước 2: Chế biến món {name}"],
                        tags=["gia đình", "nhanh gọn"],
                        match_score=0.8
                    )
                    recipes.append(recipe)
            
            search_time = (datetime.now() - start_time).total_seconds()
            
            return RecipeSearchResult(
                recipes=recipes,
                total_found=len(recipes),
                search_time=search_time,
                suggestions=[r.name for r in recipes]
            )
            
        except Exception:
            return RecipeSearchResult(
                recipes=[],
                total_found=0,
                search_time=0,
                suggestions=[]
            )
    
    def get_recipe_details(self, recipe_name: str) -> Optional[Recipe]:
        """Lấy chi tiết công thức nấu ăn"""
        try:
            prompt = f"""Hướng dẫn nấu món "{recipe_name}" chi tiết.
Format:
NGUYÊN LIỆU:
- Nguyên liệu 1: số lượng
- Nguyên liệu 2: số lượng

CÁCH LÀM:
1. Bước đầu tiên
2. Bước tiếp theo
3. Hoàn thành

THÔNG TIN:
- Thời gian chuẩn bị: X phút
- Thời gian nấu: Y phút  
- Khẩu phần: Z người
- Độ khó: dễ/trung bình/khó"""
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt
            )
            
            if response.text:
                # Parse response để tạo Recipe object
                text = response.text.strip()
                
                # Extract basic info
                prep_time = 15
                cook_time = 30
                servings = 2
                difficulty = "medium"
                
                # Simple parsing
                if "Thời gian chuẩn bị:" in text:
                    try:
                        prep_match = text.split("Thời gian chuẩn bị:")[1].split("phút")[0]
                        prep_time = int(''.join(filter(str.isdigit, prep_match)))
                    except:
                        pass
                
                if "Thời gian nấu:" in text:
                    try:
                        cook_match = text.split("Thời gian nấu:")[1].split("phút")[0]
                        cook_time = int(''.join(filter(str.isdigit, cook_match)))
                    except:
                        pass
                
                # Extract instructions
                instructions = []
                if "CÁCH LÀM:" in text:
                    steps_section = text.split("CÁCH LÀM:")[1].split("THÔNG TIN:")[0]
                    for line in steps_section.strip().split('\n'):
                        if line.strip() and (line.strip().startswith(tuple('123456789'))):
                            instructions.append(line.strip())
                
                # Extract ingredients
                ingredients_needed = []
                if "NGUYÊN LIỆU:" in text:
                    ing_section = text.split("NGUYÊN LIỆU:")[1].split("CÁCH LÀM:")[0]
                    for line in ing_section.strip().split('\n'):
                        if line.strip() and line.strip().startswith('-'):
                            parts = line.strip()[1:].split(':')
                            if len(parts) >= 2:
                                ingredients_needed.append({
                                    "name": parts[0].strip(),
                                    "quantity": parts[1].strip(),
                                    "unit": "gram"
                                })
                
                return Recipe(
                    id=f"recipe_{hash(recipe_name)}",
                    name=recipe_name,
                    description=f"Hướng dẫn chi tiết cách nấu {recipe_name}",
                    prep_time=prep_time,
                    cook_time=cook_time,
                    total_time=prep_time + cook_time,
                    servings=servings,
                    difficulty=difficulty,
                    cuisine_type="vietnamese",
                    ingredients_needed=ingredients_needed,
                    instructions=instructions,
                    tags=["truyền thống", "gia đình"]
                )
            
            return None
            
        except Exception:
            return None
    
    def suggest_meal_plan(self, 
                         available_ingredients: List[str],
                         days: int = 7,
                         meals_per_day: int = 3) -> Dict[str, Any]:
        """Gợi ý thực đơn cho nhiều ngày"""
        try:
            prompt = f"""Từ nguyên liệu: {', '.join(available_ingredients)}
Lập thực đơn {days} ngày, mỗi ngày {meals_per_day} bữa (sáng, trưa, tối).

Format:
NGÀY 1:
Sáng: Món ăn sáng
Trưa: Món ăn trưa  
Tối: Món ăn tối

NGÀY 2:
...

CẦN MUA THÊM:
- Nguyên liệu 1
- Nguyên liệu 2"""
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt
            )
            
            if response.text:
                # Simple parsing meal plan
                meal_plan = {}
                shopping_list = []
                
                text = response.text.strip()
                
                # Parse meal plan (simplified)
                lines = text.split('\n')
                current_day = None
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('NGÀY'):
                        current_day = line.lower().replace(' ', '_').replace(':', '')
                        meal_plan[current_day] = {}
                    elif current_day and ':' in line:
                        parts = line.split(':', 1)
                        meal_type = parts[0].strip().lower()
                        meal_name = parts[1].strip()
                        meal_plan[current_day][meal_type] = {
                            "name": meal_name,
                            "prep_time": 20
                        }
                    elif line.startswith('-') and 'CẦN MUA' in text:
                        item = line[1:].strip()
                        shopping_list.append({
                            "item": item,
                            "quantity": "vừa đủ",
                            "priority": "medium"
                        })
                
                return {
                    "meal_plan": meal_plan,
                    "shopping_list": shopping_list
                }
            
            return {"meal_plan": {}, "shopping_list": []}
            
        except Exception:
            return {"meal_plan": {}, "shopping_list": []}

# ============================================================================
# API CLASS
# ============================================================================

class CookingAPI:
    def __init__(self, api_key: str):
        self.service = AICookingService(api_key)
    
    def to_dict(self, obj) -> Dict[str, Any]:
        """Convert dataclass to dict"""
        if hasattr(obj, '__dict__'):
            return asdict(obj)
        return obj
    
    def correct_ingredient_endpoint(self, raw_name: str) -> Dict[str, Any]:
        """API endpoint: sửa chính tả nguyên liệu"""
        corrected = self.service.correct_ingredient_name(raw_name)
        return {
            "original": raw_name,
            "corrected": corrected,
            "category": self.service.categorize_ingredient(corrected)
        }
    
    def suggest_ingredients_endpoint(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """API endpoint: gợi ý nguyên liệu"""
        suggestions = self.service.suggest_ingredients(query, limit)
        return {
            "query": query,
            "suggestions": [self.to_dict(s) for s in suggestions]
        }
    
    def search_recipes_endpoint(self, 
                               ingredients: List[str],
                               max_results: int = 10,
                               difficulty: Optional[str] = None,
                               max_cook_time: Optional[int] = None) -> Dict[str, Any]:
        """API endpoint: tìm kiếm công thức"""
        result = self.service.search_recipes_by_ingredients(
            ingredients, max_results, difficulty, max_cook_time
        )
        return self.to_dict(result)
    
    def get_recipe_endpoint(self, recipe_name: str) -> Dict[str, Any]:
        """API endpoint: lấy chi tiết công thức"""
        recipe = self.service.get_recipe_details(recipe_name)
        if recipe:
            return self.to_dict(recipe)
        return {"error": "Không tìm thấy công thức"}
    
    def meal_plan_endpoint(self, 
                          ingredients: List[str],
                          days: int = 7,
                          meals_per_day: int = 3) -> Dict[str, Any]:
        """API endpoint: gợi ý thực đơn"""
        return self.service.suggest_meal_plan(ingredients, days, meals_per_day)

# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Khởi tạo API
    api = CookingAPI("AIzaSyAZJL6ixCrGbjn9x7ZtXimRhxjb-51Xxzg")
    
    print("=== Test Ingredient Correction ===")
    result = api.correct_ingredient_endpoint("ca chua")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n=== Test Ingredient Suggestions ===")
    result = api.suggest_ingredients_endpoint("thịt", 5)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n=== Test Recipe Search ===")
    result = api.search_recipes_endpoint(
        ingredients=["thịt bò", "cà chua", "hành tây"],
        max_results=3,
        difficulty="easy"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n=== Test Recipe Details ===")
    result = api.get_recipe_endpoint("bò xào cà chua")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n=== Test Meal Plan ===")
    result = api.meal_plan_endpoint(
        ingredients=["thịt bò", "cà chua", "rau muống"],
        days=3,
        meals_per_day=2
    )
    print(json.dumps(result, indent=2, ensure_ascii=False)) 