import axios from "axios"

export const apiClient = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
    headers: {"Content-Type": "application/json"},
    timeout: 120000,
});


apiClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem("auth_token");
        if (token) {
            config.headers = {
                ...config.headers,
                Authorization: `Bearer ${token}`,
            };
        }
        return config;
    },
    (err) => {
        if(err?.response?.status === 401){
            localStorage.removeItem("auth_token");
            if(window.location.pathname !== "/login"){
                window.location.assign("/login");
            }
        }
        return Promise.reject(err);
    }
);

apiClient.interceptors.response.use(
    (response) => response,
    (err) => {
        if(err?.response?.status === 401){
            localStorage.removeItem("auth_token");
            if(window.location.pathname !== "/login"){
                window.location.assign("/login");
            }
        }
        return Promise.reject(err);
    }
);

//POST /auth/register -> {token, user: {id, name, email}}
export async function registerRequest({email, password, fullName}){
    const {data} = await apiClient.post("/auth/register", {email, password, full_name: fullName});
    return data;
}

// POST /auth/login -> {token, user: {id, name, email}}
export async function loginRequest({email, password}){
    const {data} = await apiClient.post("/auth/login", {email,password});
    return data;
}

// GET /auth/me -> {id, name, email}
export async function fetchCurrentUser(){
    const {data} = await apiClient.get("/auth/me");
    return data;
} 


// POST /auth/logout
export async function logoutRequest(){
    await apiClient.post("/auth/logout")
}

// POST /chat/ask -> {sessionId, answer, parts, usedSources, citations}
export async function askQuestion({question, sourceIds, sessionId, provider}){
    const {data} = await apiClient.post("/chat/ask",{question, sourceIds, sessionId, provider});
    return data;
}

export async function fetchSessions(){
    const {data} = await apiClient.get("/chat/sessions");
    return data;
}

export async function createSession(title){
    const {data} = await apiClient.post("/chat/sessions", {title,});
    return data;
}

export async function fetchSessionMessages(sessionId){
    const {data} = await apiClient.get(`/chat/sessions/${sessionId}/messages`);
    return data;
}

//GET /chat/messages
export async function fetchMessages(){
    const {data} = await apiClient.get("/chat/messages");
    return data;
}

// GET /sources -> [{id, name, meta, type}]
export async function fetchSources(sessionId){
    const {data} = await apiClient.get("/sources/", {params: sessionId ? {sessionId} : {}});
    return data;
}


// POST /sources (multipart/from-data) -> upload source metadata
export async function uploadSource({file, url, sessionId}){
    const form = new FormData();
    if (file) form.append("file", file);
    if (url) form.append("url", url);
    if (sessionId) form.append("sessionId", sessionId);
    const {data} = await apiClient.post("/sources/upload", form,{
        headers: {
            "Content-Type": "multipart/form-data"
        },
    })
    return data;
}
