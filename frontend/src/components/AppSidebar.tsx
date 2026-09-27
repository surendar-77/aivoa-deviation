/**
 * App navigation, built from shadcn/ui Sidebar primitives (sidebar-07 / dashboard-01 pattern):
 * brand, a primary "New deviation" quick action, and the three places a QA reviewer goes.
 * Collapses to icons (with tooltips) on desktop and becomes a sheet on mobile.
 */
import { CirclePlus, FileText, History, Moon, ShieldCheck, Sun } from "lucide-react"
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader,
  SidebarMenu, SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarRail,
} from "@/components/ui/sidebar"

type Props = {
  currentId: string | null
  savedCount: number
  newDisabled: boolean
  theme: "light" | "dark"
  onNew: () => void
  onRecent: () => void
  onAudit: () => void
  onToggleTheme: () => void
}

export default function AppSidebar({ currentId, savedCount, newDisabled, theme, onNew, onRecent, onAudit, onToggleTheme }: Props) {
  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" className="pointer-events-none" tabIndex={-1}>
              <span className="brand-logo" aria-hidden="true">A</span>
              <span className="flex min-w-0 flex-1 flex-col text-left leading-tight">
                <span className="truncate font-semibold">AIVOA QMS</span>
                <span className="truncate text-xs text-muted-foreground">Quality issue reporting</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent className="flex flex-col gap-2">
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="New deviation"
                  onClick={onNew}
                  disabled={newDisabled}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground active:bg-primary/90 active:text-primary-foreground"
                >
                  <CirclePlus />
                  <span>New deviation</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Deviations</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton tooltip="Current report" isActive>
                  <FileText />
                  <span>Current report</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton tooltip="Saved reports" onClick={onRecent}>
                  <History />
                  <span>Saved reports</span>
                </SidebarMenuButton>
                {savedCount > 0 && <SidebarMenuBadge>{savedCount}</SidebarMenuBadge>}
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip={currentId ? `Change history for ${currentId}` : "Change history (available after the first save)"}
                  onClick={onAudit}
                  disabled={!currentId}
                >
                  <ShieldCheck />
                  <span>Change history</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip={theme === "dark" ? "Light theme" : "Dark theme"} onClick={onToggleTheme}>
              {theme === "dark" ? <Sun /> : <Moon />}
              <span>{theme === "dark" ? "Light theme" : "Dark theme"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
