import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchCinemas, fetchMovies, fetchShows } from "../lib/catalogApi";
import { setRuntimeCinemas } from "../lib/cinemas";

const AppContext = createContext();

export const AppProvider = (props) => {
  const [movies, setMovies] = useState([]);
  const [showtimes, setShowtimes] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const refreshCatalog = useCallback(async () => {
    setIsLoading(true);
    try {
      const [movieList, showList, vendorList] = await Promise.all([
        fetchMovies(),
        fetchShows(),
        fetchCinemas(),
      ]);

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
  }, []);

  useEffect(() => {
    refreshCatalog();
  }, [refreshCatalog]);

  return (
    <AppContext.Provider
      value={{
        movies,
        showtimes,
        vendors,
        isLoading,
        refreshCatalog,
      }}
    >
      {props.children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
