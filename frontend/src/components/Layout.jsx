import React from "react";
import { useLocation } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";

export default function Layout({ children }) {
  const location = useLocation();
  const path = String(location?.pathname || "").toLowerCase();
  const hideFooter = path === "/payment-success" || path === "/payment-failure";

  return (
    <>
      <Header />
      <main>{children}</main>
      {!hideFooter ? <Footer /> : null}
    </>
  );
}
