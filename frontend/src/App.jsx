import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import Movies from "./pages/Movies";
import MovieDetails from "./pages/MovieDetails";
import MovieSchedule from "./pages/MovieSchedule";
import Schedules from "./pages/Schedules";
import SeatSelection from "./pages/SeatSelection";
import Cinemas from "./pages/Cinemas";
import Layout from "./components/Layout";


function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout><Home /></Layout>} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/movie/:id" element={<Layout><MovieDetails /></Layout>} />
        <Route path="/movie/:id/schedule" element={<Layout><MovieSchedule /></Layout>} />
        <Route path="/movies" element={<Layout><Movies /></Layout>} />
        <Route path="/schedules" element={<Layout><Schedules /></Layout>} />
        <Route path="/cinemas" element={<Layout><Cinemas /></Layout>} />
        <Route path="/cinemas/:vendor" element={<Layout><Schedules /></Layout>} />
        <Route path="/booking" element={<Layout><SeatSelection /></Layout>} />
        <Route path="/home" element={<Layout><Home /></Layout>} />
        <Route path="/dashboard" element={<Layout><Home /></Layout>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
