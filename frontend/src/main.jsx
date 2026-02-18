import { createRoot } from "react-dom/client";
import "./index.css";
import "./css/admin.css";
import "./css/vendor.css";
import App from "./App.jsx";
import { AppProvider } from "./context/Appcontext";

createRoot(document.getElementById('root')).render(
    <AppProvider>
      <App />
    </AppProvider>
)
