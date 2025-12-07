import axios from "axios";
import { API_BASE_URL } from "./constants.js";

/**
 * Create an axios instance with default headers
 * for API calls to the backend
 */
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
  withCredentials: false, // Don't send cookies with requests
});

// Optional: Add a request interceptor for logging/debugging
apiClient.interceptors.request.use(
  (config) => {
    // You can log or modify requests here
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Optional: Add a response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Handle common errors here
    if (error.response?.status === 401) {
      // Handle unauthorized - redirect to login
      console.warn("Unauthorized - redirecting to login");
    }
    return Promise.reject(error);
  }
);

export default apiClient;
