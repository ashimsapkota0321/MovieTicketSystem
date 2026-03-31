import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchCinemas, fetchMovies, fetchShows } from "../lib/catalogApi";
import { getAuthSession, getRoleFromPath } from "../lib/authSession";
import { setRuntimeCinemas } from "../lib/cinemas";

const AppContext = createContext();
const LOCATION_STORAGE_KEY = "mt_selected_location";

function getInitialLocation() {
  if (typeof window === "undefined") return "";
  const stored = String(window.localStorage.getItem(LOCATION_STORAGE_KEY) || "").trim();
  return stored || "";
}

function shouldScopeCatalogByCity() {
  if (typeof window === "undefined") return true;
  const role = getRoleFromPath(window.location?.pathname || "");
  if (role === "admin" || role === "vendor") return false;

  // Handle login transition where role session is already stored but route not changed yet.
  if (getAuthSession("admin")?.role === "admin") return false;
  if (getAuthSession("vendor")?.role === "vendor") return false;

  return true;
}

export const AppProvider = (props) => {
  const [movies, setMovies] = useState([]);
  const [showtimes, setShowtimes] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedLocation, setSelectedLocation] = useState(getInitialLocation);

  const refreshCatalog = useCallback(async () => {
    setIsLoading(true);
    try {
      const scopeByCity = shouldScopeCatalogByCity();
      const scopedParams =
        scopeByCity && selectedLocation ? { city: selectedLocation } : {};
      let [movieList, showList, vendorList] = await Promise.all([
        fetchMovies(scopedParams),
        fetchShows(scopedParams),
        fetchCinemas(scopedParams),
      ]);

      // If the chosen city has no catalog entries, fall back to all cities.
      if (
        scopeByCity &&
        selectedLocation &&
        (!Array.isArray(movieList) || movieList.length === 0) &&
        (!Array.isArray(showList) || showList.length === 0)
      ) {
        const [fallbackMovies, fallbackShows, fallbackVendors] = await Promise.all([
          fetchMovies({}),
          fetchShows({}),
          fetchCinemas({}),
        ]);
        const hasFallbackData =
          (Array.isArray(fallbackMovies) && fallbackMovies.length > 0) ||
          (Array.isArray(fallbackShows) && fallbackShows.length > 0) ||
          (Array.isArray(fallbackVendors) && fallbackVendors.length > 0);
        if (hasFallbackData) {
          movieList = fallbackMovies;
          showList = fallbackShows;
          vendorList = fallbackVendors;
          setSelectedLocation("");
        }
      }

      setMovies(movieList || []);
      setShowtimes(showList || []);
      setVendors(vendorList || []);

      if (Array.isArray(vendorList)) {
        setRuntimeCinemas(
          vendorList.map((vendor) => ({
            name: vendor.name,
            slug: vendor.slug,
            short: vendor.short,
            locations: [vendor.theatre || vendor.city || "Kathmandu"],
            accent: vendor.accent,
          }))
        );
      }
    } catch (error) {
      console.log(error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedLocation]);

  useEffect(() => {
    refreshCatalog();
  }, [refreshCatalog]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleAuthOrRoleUpdate = () => {
      refreshCatalog();
    };
    window.addEventListener("mt:user-updated", handleAuthOrRoleUpdate);
    window.addEventListener("mt:admin-updated", handleAuthOrRoleUpdate);
    window.addEventListener("mt:vendor-updated", handleAuthOrRoleUpdate);
    return () => {
      window.removeEventListener("mt:user-updated", handleAuthOrRoleUpdate);
      window.removeEventListener("mt:admin-updated", handleAuthOrRoleUpdate);
      window.removeEventListener("mt:vendor-updated", handleAuthOrRoleUpdate);
    };
  }, [refreshCatalog]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(LOCATION_STORAGE_KEY, selectedLocation || "");
  }, [selectedLocation]);

  return (
    <AppContext.Provider
      value={{
        movies,
        showtimes,
        vendors,
        isLoading,
        selectedLocation,
        setSelectedLocation,
        refreshCatalog,
      }}
    >
      {props.children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
