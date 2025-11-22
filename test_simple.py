from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "alive", "message": "Minimal FastAPI working"}

@app.get("/test")
def test():
    return {"test": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
