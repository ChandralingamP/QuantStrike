import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import HomePage from "./pages/HomePage.jsx";
import InstrumentsPage from "./pages/InstrumentsPage.jsx";
import ProfitLossPage from "./pages/ProfitLossPage.jsx";
import AlgoConfigurationPage from "./pages/AlgoConfigurationPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SignupPage from "./pages/SignupPage.jsx";
import VerifyOtpPage from "./pages/VerifyOtpPage.jsx";
import ForgotPasswordPage from "./pages/ForgotPasswordPage.jsx";
import VerifyResetOtpPage from "./pages/VerifyResetOtpPage.jsx";
import ResetPasswordPage from "./pages/ResetPasswordPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import StrategyBacktestPage from "./pages/StrategyBacktestPage.jsx";
import LogsViewerPage from "./pages/LogsViewerPage.jsx";

export default function App() {
  return (
    <BrowserRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/verify-otp" element={<VerifyOtpPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route
          path="/forgot-password/verify"
          element={<VerifyResetOtpPage />}
        />
        <Route path="/forgot-password/reset" element={<ResetPasswordPage />} />

        {/* Standalone log viewer - no layout, accessible via direct URL only */}
        <Route path="/logs" element={<LogsViewerPage />} />

        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="instruments" element={<InstrumentsPage />} />
          <Route path="pnl" element={<ProfitLossPage />} />
          <Route path="algo" element={<AlgoConfigurationPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="admin/backtest" element={<StrategyBacktestPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
