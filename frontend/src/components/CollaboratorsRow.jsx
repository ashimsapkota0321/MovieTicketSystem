import { useEffect, useState } from "react";
import api from "../api/api";
import "../css/collaborators.css";

export default function CollaboratorsRow() {
  const [collaborators, setCollaborators] = useState([]);

  useEffect(() => {
    let mounted = true;
    const loadCollaborators = async () => {
      try {
        const response = await api.get("/api/home/collaborators/");
        if (!mounted) return;
        setCollaborators(response?.data?.collaborators || []);
      } catch (error) {
        if (!mounted) return;
        setCollaborators([]);
      }
    };
    loadCollaborators();
    return () => {
      mounted = false;
    };
  }, []);

  if (!collaborators.length) return null;

  return (
    <section className="qfx-collaborators">
      <div className="qfx-collaborators-inner">
        {collaborators.map((partner) => {
          const logo = (
            <img
              src={partner.logo}
              alt={partner.name}
              className="qfx-collaborator-logo"
              loading="lazy"
              decoding="async"
            />
          );
          return partner.website_url ? (
            <a
              key={partner.id}
              href={partner.website_url}
              className="qfx-collaborator"
              target="_blank"
              rel="noreferrer"
            >
              {logo}
            </a>
          ) : (
            <div key={partner.id} className="qfx-collaborator">
              {logo}
            </div>
          );
        })}
      </div>
    </section>
  );
}

