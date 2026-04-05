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

  const resolveSettledList = (settledResult) => {
    if (!settledResult || settledResult.status !== "fulfilled") return [];
    return Array.isArray(settledResult.value) ? settledResult.value : [];
  };

  const loadCatalogLists = async (params) => {
    const [moviesResult, showsResult, cinemasResult] = await Promise.allSettled([
      fetchMovies(params),
      fetchShows(params),
      fetchCinemas(params),
    ]);

    return {
      movieList: resolveSettledList(moviesResult),
      showList: resolveSettledList(showsResult),
      vendorList: resolveSettledList(cinemasResult),
    };
  };

  const refreshCatalog = useCallback(async () => {
    setIsLoading(true);
    try {
      const scopeByCity = shouldScopeCatalogByCity();
      const scopedParams =
        scopeByCity && selectedLocation ? { city: selectedLocation } : {};

      let { movieList, showList, vendorList } = await loadCatalogLists(scopedParams);

      // If city-scoped queries return no catalog data, retry without city scope.
      const shouldRetryUnscoped =
        scopeByCity &&
        Boolean(selectedLocation) &&
        movieList.length === 0 &&
        showList.length === 0 &&
        vendorList.length === 0;

      if (shouldRetryUnscoped) {
        const fallback = await loadCatalogLists({});
        movieList = fallback.movieList;
        showList = fallback.showList;
        vendorList = fallback.vendorList;
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
