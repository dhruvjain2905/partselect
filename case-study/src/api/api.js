const API_BASE = "http://localhost:8000/api/v1";

export const createSessionId = () => crypto.randomUUID().slice(0, 12);

export const getAIMessage = async (userQuery, sessionId) => {
  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: userQuery,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();

    return {
      role: "assistant",
      content: data.reply,
      products: data.products || [],
      context: data.context || {},
    };
  } catch (error) {
    console.error("Chat API error:", error);
    return {
      role: "assistant",
      content:
        "I'm having trouble connecting right now. Please make sure the backend server is running (`uvicorn app.main:app --reload`) and try again.",
      products: [],
      context: {},
    };
  }
};
