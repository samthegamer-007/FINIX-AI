import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { auth } from "./api.js";
import Landing from "./pages/Landing.jsx";
import Auth from "./pages/Auth.jsx";
import Chat from "./pages/Chat.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import AdminGate from "./pages/AdminGate.jsx";
import AdminDashboard from "./pages/AdminDashboard.jsx";

function Private({ children }) {
  return auth.get() ? children : <Navigate to="/auth" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/auth" element={<Auth />} />
      <Route path="/chat/:chatId?" element={<Private><Chat /></Private>} />
      <Route path="/portfolio" element={<Private><Portfolio /></Private>} />
      <Route path="/admin" element={<AdminGate />} />
      <Route path="/admin-dashboard" element={<AdminDashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
