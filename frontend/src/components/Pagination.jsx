import React from "react";
import "./Pagination.css";

export default function Pagination({ page, totalPages, onPageChange }) {
  const safeTotalPages = Math.max(1, Number(totalPages) || 1);
  const safePage = Math.min(Math.max(1, Number(page) || 1), safeTotalPages);
  const pages = [];
  for (let i = 1; i <= safeTotalPages; i++) {
    pages.push(i);
  }

  return (
    <div className="custom-pagination">
      <button
        className="page-btn"
        onClick={() => onPageChange(safePage - 1)}
        disabled={safePage === 1}
      >
        Prev
      </button>
      {pages.map((p) => (
        <button
          key={p}
          className={`page-btn${p === safePage ? " active" : ""}`}
          onClick={() => onPageChange(p)}
        >
          {p}
        </button>
      ))}
      <button
        className="page-btn"
        onClick={() => onPageChange(safePage + 1)}
        disabled={safePage === safeTotalPages}
      >
        Next
      </button>
    </div>
  );
}
