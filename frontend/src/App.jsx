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
import EsewaCheckout from "./pages/EsewaCheckout";
import PaymentSuccess from "./pages/PaymentSuccess";
import PaymentFailure from "./pages/PaymentFailure";
import WalletTopupEsewaCheckout from "./pages/WalletTopupEsewaCheckout";
import WalletTopupSuccess from "./pages/WalletTopupSuccess";
import WalletTopupFailure from "./pages/WalletTopupFailure";
import Layout from "./components/Layout";
import Profile from "./pages/Profile";
import BookingHistory from "./pages/BookingHistory";
import Notifications from "./pages/Notifications";
import LoyaltyDashboard from "./pages/LoyaltyDashboard";
import LoyaltyRewards from "./pages/LoyaltyRewards";
import ReferralWallet from "./pages/ReferralWallet";
import SubscriptionPlans from "./pages/SubscriptionPlans";
import SubscriptionPlanDetail from "./pages/SubscriptionPlanDetail";
import SubscriptionDashboard from "./pages/SubscriptionDashboard";
import GroupBookingCreate from "./pages/GroupBookingCreate";
import GroupBookingSession from "./pages/GroupBookingSession";
import NotFound from "./pages/NotFound";
import AdminLayout from "./admin/AdminLayout";
import AdminDashboard from "./admin/AdminDashboard";
import AdminMovies from "./admin/AdminMovies";
import AdminBanners from "./admin/AdminBanners";
import AdminVendors from "./admin/AdminVendors";
import AdminUsers from "./admin/AdminUsers";
import AdminShows from "./admin/AdminShows";
import AdminSchedule from "./admin/AdminSchedule";
import AdminReviews from "./admin/AdminReviews";
import AdminBookings from "./admin/AdminBookings";
import AdminReports from "./admin/AdminReports";
import AdminProfile from "./admin/AdminProfile";
import AdminPeople from "./admin/AdminPeople";
import AdminTrailers from "./admin/AdminTrailers";
import AdminCoupons from "./admin/AdminCoupons";
import AdminLoyaltyControl from "./admin/AdminLoyaltyControl";
import AdminSubscriptionControl from "./admin/AdminSubscriptionControl";
import AdminReferralControl from "./admin/AdminReferralControl";
import VendorLayout from "./vendor/VendorLayout";
import VendorDashboard from "./vendor/VendorDashboard";
import VendorProfile from "./vendor/VendorProfile";
import VendorShows from "./vendor/VendorShows";
import VendorFoodItems from "./vendor/VendorFoodItems";
import VendorSeats from "./vendor/VendorSeats";
import VendorBookings from "./vendor/VendorBookings";
import VendorPricingRules from "./vendor/VendorPricingRules";
import VendorTicketValidation from "./vendor/VendorTicketValidation";
import VendorCorporateBulkBookings from "./vendor/VendorCorporateBulkBookings";
import VendorStaffAccounts from "./vendor/VendorStaffAccounts";
import VendorCampaignPromos from "./vendor/VendorCampaignPromos";
import VendorOffers from "./vendor/VendorOffers";
import { canAccessVendorFeature, getAuthSession } from "./lib/authSession";

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

function RequireAuth({ children }) {
  const auth = getAuthSession();
  if (!auth?.role) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RequireCustomer({ children }) {
  const auth = getAuthSession("customer");
  if (!auth?.role || auth.role !== "customer" || !auth?.token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RequireVendorFeature({ feature, children }) {
  const auth = getAuthSession("vendor");
  if (!auth?.role || auth.role !== "vendor") {
    return <Navigate to="/login" replace />;
  }
  if (!canAccessVendorFeature(feature)) {
    return <Navigate to="/vendor/bookings" replace />;
  }
  return children;
}

function VendorDefaultRoute() {
  if (canAccessVendorFeature("dashboard")) {
    return <Navigate to="dashboard" replace />;
  }
  if (canAccessVendorFeature("bookings")) {
    return <Navigate to="bookings" replace />;
  }
  return <Navigate to="ticket-validation" replace />;
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
        <Route path="/esewa/checkout" element={<Layout><EsewaCheckout /></Layout>} />
        <Route path="/payment-success" element={<Layout><PaymentSuccess /></Layout>} />
        <Route path="/payment-failure" element={<Layout><PaymentFailure /></Layout>} />
        <Route
          path="/wallet/topup/esewa/checkout"
          element={
            <RequireCustomer>
              <Layout><WalletTopupEsewaCheckout /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/wallet/topup/success"
          element={
            <RequireCustomer>
              <Layout><WalletTopupSuccess /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/wallet/topup/failure"
          element={
            <RequireCustomer>
              <Layout><WalletTopupFailure /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/booking"
          element={
            <RequireAuth>
              <Layout><SeatSelection /></Layout>
            </RequireAuth>
          }
        />
        <Route path="/home" element={<Layout><Home /></Layout>} />
        <Route path="/dashboard" element={<Layout><Home /></Layout>} />
        <Route path="/profile" element={<Layout><Profile /></Layout>} />
        <Route
          path="/bookings/history"
          element={
            <RequireCustomer>
              <Layout><BookingHistory /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/notifications"
          element={
            <RequireCustomer>
              <Layout><Notifications /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/loyalty/dashboard"
          element={
            <RequireCustomer>
              <Layout><LoyaltyDashboard /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/loyalty/rewards"
          element={
            <RequireCustomer>
              <Layout><LoyaltyRewards /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/referral/wallet"
          element={
            <RequireCustomer>
              <Layout><ReferralWallet /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/subscriptions/plans"
          element={
            <RequireCustomer>
              <Layout><SubscriptionPlans /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/subscriptions/plans/:planId"
          element={
            <RequireCustomer>
              <Layout><SubscriptionPlanDetail /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/subscriptions/dashboard"
          element={
            <RequireCustomer>
              <Layout><SubscriptionDashboard /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/group-booking/new"
          element={
            <RequireCustomer>
              <Layout><GroupBookingCreate /></Layout>
            </RequireCustomer>
          }
        />
        <Route
          path="/group-booking/session/:inviteCode"
          element={
            <RequireCustomer>
              <Layout><GroupBookingSession /></Layout>
            </RequireCustomer>
          }
        />
        <Route path="/admin" element={<RequireRole allowedRole="admin"><AdminLayout /></RequireRole>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="banners" element={<AdminBanners />} />
          <Route path="trailers" element={<AdminTrailers />} />
          <Route path="movies" element={<AdminMovies />} />
          <Route path="people" element={<AdminPeople />} />
          <Route path="vendors" element={<AdminVendors />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="shows" element={<AdminShows />} />
          <Route path="schedule" element={<AdminSchedule />} />
          <Route path="reviews" element={<AdminReviews />} />
          <Route path="bookings" element={<AdminBookings />} />
          <Route path="coupons" element={<AdminCoupons />} />
          <Route path="loyalty" element={<AdminLoyaltyControl />} />
          <Route path="subscriptions" element={<AdminSubscriptionControl />} />
          <Route path="referrals" element={<AdminReferralControl />} />
          <Route path="reports" element={<AdminReports />} />
          <Route path="profile" element={<AdminProfile />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="/vendor" element={<RequireRole allowedRole="vendor"><VendorLayout /></RequireRole>}>
          <Route index element={<VendorDefaultRoute />} />
          <Route path="dashboard" element={<RequireVendorFeature feature="dashboard"><VendorDashboard /></RequireVendorFeature>} />
          <Route path="shows" element={<RequireVendorFeature feature="shows"><VendorShows /></RequireVendorFeature>} />
          <Route path="food" element={<RequireVendorFeature feature="food"><VendorFoodItems /></RequireVendorFeature>} />
          <Route path="seats" element={<RequireVendorFeature feature="seats"><VendorSeats /></RequireVendorFeature>} />
          <Route path="pricing" element={<RequireVendorFeature feature="pricing"><VendorPricingRules /></RequireVendorFeature>} />
          <Route path="bookings" element={<RequireVendorFeature feature="bookings"><VendorBookings /></RequireVendorFeature>} />
          <Route path="corporate-bulk" element={<RequireVendorFeature feature="corporate-bulk"><VendorCorporateBulkBookings /></RequireVendorFeature>} />
          <Route path="campaigns-promos" element={<RequireVendorFeature feature="campaigns-promos"><VendorCampaignPromos /></RequireVendorFeature>} />
          <Route path="offers" element={<RequireVendorFeature feature="offers"><VendorOffers /></RequireVendorFeature>} />
          <Route path="ticket-validation" element={<RequireVendorFeature feature="ticket-validation"><VendorTicketValidation /></RequireVendorFeature>} />
          <Route path="staff-accounts" element={<RequireVendorFeature feature="staff-accounts"><VendorStaffAccounts /></RequireVendorFeature>} />
          <Route path="profile" element={<RequireVendorFeature feature="profile"><VendorProfile /></RequireVendorFeature>} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<Layout><NotFound /></Layout>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
