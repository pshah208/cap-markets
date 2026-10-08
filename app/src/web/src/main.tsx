import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initAuth } from "./auth";
import { applyBrand } from "./brand";
import "./styles.css";

applyBrand();

initAuth()
  .catch((e) => console.error("auth init failed", e))
  .finally(() => {
    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
  });
