import {useState, useCallback, useEffect} from "react"
import { loginRequest, fetchCurrentUser, logoutRequest, registerRequest } from "../api/client"
import { AuthContext } from "./authContextValue";

const TOKEN_KEY = "auth_token";

export function AuthProvider({children}){
    const [user, setUser] = useState(null);
    const [token, setToken] = useState(()=> localStorage.getItem(TOKEN_KEY));
    const [loading, setLoading] = useState(Boolean(token));
    const [error, setError] = useState(null);
    const [error1, setError1] = useState(null);

    useEffect(()=>{
        if(!token) return;
        fetchCurrentUser()
            .then((u)=>setUser(u))
            .catch(()=>{
                localStorage.removeItem(TOKEN_KEY);
                setUser(null); 
                setToken(null);
            })
            .finally(()=> setLoading(false));
    },[token]);

    const register = useCallback(async({email, password, fullName})=>{
        setError1(null);
        try{
            const {token: newToken, user: newUser} = await registerRequest({email, password, fullName});
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
            localStorage.removeItem("sources");
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
