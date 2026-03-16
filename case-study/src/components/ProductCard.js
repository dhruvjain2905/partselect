import React from "react";
import "./ProductCard.css";

function ProductCard({ product }) {
  const { ps_number, name, price, in_stock, product_url, category, fix_rate_pct } = product;

  return (
    <a
      href={product_url || "#"}
      target="_blank"
      rel="noopener noreferrer"
      className="product-card"
    >
      <div className="product-card-top">
        <span className="product-ps">{ps_number}</span>
        {in_stock !== null && in_stock !== undefined && (
          <span className={`product-stock ${in_stock ? "in-stock" : "out-stock"}`}>
            {in_stock ? "In Stock" : "Out of Stock"}
          </span>
        )}
      </div>
      <div className="product-name">{name}</div>
      {category && <div className="product-category">{category}</div>}
      <div className="product-card-bottom">
        <div className="product-meta">
          {price && <span className="product-price">${parseFloat(price).toFixed(2)}</span>}
          {fix_rate_pct && (
            <span className="product-fix">{Math.round(fix_rate_pct)}% fix rate</span>
          )}
        </div>
        <span className="product-cta">
          View Part
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
      </div>
    </a>
  );
}

function ProductCardList({ products }) {
  if (!products || products.length === 0) return null;
  return (
    <div className="product-list">
      {products.map((p) => (
        <ProductCard key={p.ps_number} product={p} />
      ))}
    </div>
  );
}

export { ProductCard, ProductCardList };
export default ProductCardList;
