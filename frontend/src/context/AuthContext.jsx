import {createContext, useContext, useState, useCallback, useEffect} from "react"
import { loginRequest, fetchCurrentUser, logoutRequest, registerRequest } from "../api/client"

const AuthContext = createContext(null);
const TOKEN_KEY = "auth_token";

export function AuthProvider({children}){
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(()=> localStorage.getItem(TOKEN_KEY));
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [error1, setError1] = useState(null);

    useEffect(()=>{
        if(!token){
            setLoading(false);
            return;
        }
        fetchCurrentUser()
            .then((u)=>setUser(u))
            .catch(()=>{
                localStorage.removeItem(TOKEN_KEY);
                setUser(null); 
                setToken(null);
            })
            .finally(()=> setLoading(false));
    },[token]);

    const register = useCallback(async({email, password, fullname})=>{
        setError1(null);
        try{
            const {token: newToken, user: newUser} = await registerRequest({email, password, fullname});
            localStorage.setItem(TOKEN_KEY, newToken);
            setUser(newUser);
            setToken(newToken);
            setLoading(false);
            return true;
        } catch(err){
            setUser(null);
            setToken(null);
            localStorage.removeItem(TOKEN_KEY);
            setError1(
                err?.response?.data?.message || "Tạo tài khoản thất bại! Vui lòng kiểm tra thông tin."
            );
            return false;
        }
    }, [])

    const login = useCallback(async({email, password})=>{
        setError(null);
        try{
            const {token: newToken, user: newUser} = await loginRequest({email, password});
            localStorage.setItem(TOKEN_KEY, newToken);
            setUser(newUser);
            setToken(newToken);
            setLoading(false);
            return true;
        } catch(err){
            setUser(null);
            setToken(null);
            localStorage.removeItem(TOKEN_KEY);
            setError(
                err?.response?.data?.message || "Email hoặc mật khẩu không đúng vui lòng nhập lại."
            );
            return false;
        }
    },[]);

    const logout = useCallback(async()=>{
        try{
            await logoutRequest();
        } catch (err){
            setError(
                err?.response?.data?.message || "Đăng xuất thất bại."
            );
        } finally {
            localStorage.removeItem(TOKEN_KEY);
            setToken(null);
            setUser(null);
        }
    }, []);

    const value = {
        user, 
        token,
        isAuthenticated: Boolean(token && user),
        loading,
        error,
        error1,
        login,
        logout,
        register,
    };

    return <AuthContext.Provider value = {value}>
        {children}
    </AuthContext.Provider>
} 

export function useAuth(){
    const ctx = useContext(AuthContext);
    if(!ctx){
        throw new Error("useAuth must be used within AuthProvider");
    }
    return ctx;
}