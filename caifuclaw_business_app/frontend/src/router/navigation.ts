import {
  useLocation as useWouterLocation,
  useSearch,
  useSearchParams
} from 'wouter'

export { useSearchParams }

export function useLocation() {
  const [pathname] = useWouterLocation()
  const search = useSearch()
  return { pathname, search: search ? `?${search}` : '' }
}

export function useNavigate() {
  const [, navigate] = useWouterLocation()
  return navigate
}
