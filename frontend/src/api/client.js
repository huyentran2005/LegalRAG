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
export async function askQuestion({question, sourceIds, sessionId}){
    const {data} = await apiClient.post("/chat/ask",{question, sourceIds, sessionId});
    return data;
}


// GET /sources -> [{id, name, meta, type}]
export async function fetchSources(){
    const {data} = await apiClient.get("/sources/");
    return data;
}


// POST /sources (multipart/from-data) -> upload source metadata
export async function uploadSource(file){
    const form = new FormData();
    form.append("file", file);
    const {data} = await apiClient.post("/sources/upload", form,{
        headers: {
            "Content-Type": "multipart/form-data"
        },
    })
    return data;
}
