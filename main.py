import ast
import operator
import math
import os
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Cloud Calculator",
    description="A responsive calculator web application designed for Google Cloud Run",
    version="1.0.0"
)

# Safe math operators and functions
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
}

class CalculationRequest(BaseModel):
    expression: str

class CalculationResponse(BaseModel):
    expression: str
    result: float | int
    display_result: str
    timestamp: str

class CalculationHistoryItem(BaseModel):
    id: int
    expression: str
    result: str
    timestamp: str

# In-memory history (last 100 items)
history_db: List[CalculationHistoryItem] = []
history_counter = 0

def safe_eval(node):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Invalid constant type in expression")
    elif isinstance(node, ast.BinOp):
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            if op_type == ast.Div and right == 0:
                raise ZeroDivisionError("Division by zero")
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported operator: {op_type.__name__}")
    elif isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            args = [safe_eval(arg) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        raise ValueError(f"Unsupported function call")
    else:
        raise ValueError("Invalid syntax in expression")

def clean_expression(expr: str) -> str:
    """Normalize symbols to Python-parseable math string."""
    cleaned = expr.replace("×", "*").replace("✕", "*").replace("X", "*").replace("x", "*")
    cleaned = cleaned.replace("÷", "/")
    cleaned = cleaned.replace("−", "-")
    cleaned = cleaned.replace("√", "sqrt")
    # Handle sqrt number syntax e.g. sqrt9 -> sqrt(9)
    import re
    cleaned = re.sub(r'sqrt\s*(\d+(\.\d+)?)', r'sqrt(\1)', cleaned)
    return cleaned

@app.get("/health")
def health_check():
    """GCP Cloud Run health check endpoint"""
    return {"status": "healthy", "service": "calculator", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/calculate", response_model=CalculationResponse)
def calculate(req: CalculationRequest):
    global history_counter
    raw_expr = req.expression.strip()
    if not raw_expr:
        raise HTTPException(status_code=400, detail="Expression cannot be empty")
    
    cleaned = clean_expression(raw_expr)
    try:
        parsed = ast.parse(cleaned, mode="eval")
        res = safe_eval(parsed)
        
        # Format display result
        if isinstance(res, float) and res.is_integer():
            final_res = int(res)
            display = str(final_res)
        elif isinstance(res, float):
            final_res = round(res, 8)
            display = f"{final_res:g}"
        else:
            final_res = res
            display = str(res)
            
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        
        # Save to history
        history_counter += 1
        history_item = CalculationHistoryItem(
            id=history_counter,
            expression=raw_expr,
            result=display,
            timestamp=timestamp_str
        )
        history_db.insert(0, history_item)
        if len(history_db) > 100:
            history_db.pop()
            
        return CalculationResponse(
            expression=raw_expr,
            result=final_res,
            display_result=display,
            timestamp=timestamp_str
        )
    except ZeroDivisionError:
        raise HTTPException(status_code=400, detail="Cannot divide by zero")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid expression: {str(e)}")

@app.get("/api/history", response_model=List[CalculationHistoryItem])
def get_history():
    return history_db

@app.delete("/api/history/{item_id}")
def delete_history_item(item_id: int):
    global history_db
    initial_len = len(history_db)
    history_db = [item for item in history_db if item.id != item_id]
    if len(history_db) == initial_len:
        raise HTTPException(status_code=404, detail="History item not found")
    return {"status": "deleted", "id": item_id}

@app.delete("/api/history")
def clear_history():
    global history_db
    history_db.clear()
    return {"status": "cleared"}

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Static files for web UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Calculator API is running. Build static assets for UI."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
