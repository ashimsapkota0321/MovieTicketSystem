import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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
import FoodBeverage from "./pages/FoodBeverage";
import OrderConfirm from "./pages/OrderConfirm";
import ThankYou from "./pages/PaymentConfirm";
import TicketDownload from "./pages/TicketDownload";
import Layout from "./components/Layout";
import Profile from "./pages/Profile";
import AdminLayout from "./admin/AdminLayout";
import AdminDashboard from "./admin/AdminDashboard";
import AdminMovies from "./admin/AdminMovies";
import AdminBanners from "./admin/AdminBanners";
import AdminVendors from "./admin/AdminVendors";
import AdminUsers from "./admin/AdminUsers";
import AdminShows from "./admin/AdminShows";
import AdminSchedule from "./admin/AdminSchedule";
import AdminBookings from "./admin/AdminBookings";
import AdminReports from "./admin/AdminReports";
import AdminProfile from "./admin/AdminProfile";
import AdminPeople from "./admin/AdminPeople";
import VendorLayout from "./vendor/VendorLayout";
import VendorDashboard from "./vendor/VendorDashboard";
import VendorProfile from "./vendor/VendorProfile";
import VendorShows from "./vendor/VendorShows";
import VendorSeats from "./vendor/VendorSeats";
import { getAuthSession } from "./lib/authSession";


function RequireRole({ allowedRole, children }) {
  const auth = getAuthSession();
  if (!auth?.role) {
    return <Navigate to="/login" replace />;
  }
  if ((allowedRole === "admin" || allowedRole === "vendor") && !auth?.token) {
    return <Navigate to="/login" replace />;
  }
  if (auth.role !== allowedRole) {
    return <Navigate to="/" replace />;
  }
  return children;
}


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
        <Route path="/food" element={<Layout><FoodBeverage /></Layout>} />
        <Route path="/order-confirm" element={<Layout><OrderConfirm /></Layout>} />
        <Route path="/thank-you" element={<Layout><ThankYou /></Layout>} />
        <Route path="/ticket-download" element={<Layout><TicketDownload /></Layout>} />
        <Route path="/payment-confirm" element={<Layout><ThankYou /></Layout>} />
        <Route path="/booking" element={<Layout><SeatSelection /></Layout>} />
        <Route path="/home" element={<Layout><Home /></Layout>} />
        <Route path="/dashboard" element={<Layout><Home /></Layout>} />
        <Route path="/profile" element={<Layout><Profile /></Layout>} />
        <Route path="/admin" element={<RequireRole allowedRole="admin"><AdminLayout /></RequireRole>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="banners" element={<AdminBanners />} />
          <Route path="movies" element={<AdminMovies />} />
          <Route path="people" element={<AdminPeople />} />
          <Route path="vendors" element={<AdminVendors />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="shows" element={<AdminShows />} />
          <Route path="schedule" element={<AdminSchedule />} />
          <Route path="bookings" element={<AdminBookings />} />
          <Route path="reports" element={<AdminReports />} />
          <Route path="profile" element={<AdminProfile />} />
        </Route>
        <Route path="/vendor" element={<RequireRole allowedRole="vendor"><VendorLayout /></RequireRole>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<VendorDashboard />} />
          <Route path="shows" element={<VendorShows />} />
          <Route path="seats" element={<VendorSeats />} />
          <Route path="profile" element={<VendorProfile />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
