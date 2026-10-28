<script>
  import { onMount, onDestroy } from 'svelte';
  import RefreshCw from 'lucide-svelte/icons/refresh-cw';
  import MapPin from 'lucide-svelte/icons/map-pin';
  import Maximize2 from 'lucide-svelte/icons/maximize-2';
  import BedDouble from 'lucide-svelte/icons/bed-double';
  import ExternalLink from 'lucide-svelte/icons/external-link';
  import Award from 'lucide-svelte/icons/award';
  import Euro from 'lucide-svelte/icons/euro';
  import Clock from 'lucide-svelte/icons/clock';
  import ArrowUp from 'lucide-svelte/icons/arrow-up';
  import ArrowDown from 'lucide-svelte/icons/arrow-down';
  import AlertCircle from 'lucide-svelte/icons/alert-circle';
  import CheckCircle2 from 'lucide-svelte/icons/check-circle-2';

  let listings = $state([]);
  let isFetching = $state(false);
  let statusBanner = $state(null);
  let searchQuery = $state('');
  let statusFilter = $state('MATCH');
  let sortBy = $state('score'); // 'score' | 'price' | 'area' | 'date'
  let sortDir = $state('desc');  // 'asc' | 'desc'
  let isLoading = $state(true);
  let loadError = $state(null);
  let lastUpdated = $state(null);
  let stats = $state({ total: 0, matches: 0, needs_review: 0 });

  let pollTimer = null;

  async function loadListings() {
    isLoading = true;
    loadError = null;
    try {
      const res = await fetch(`/api/listings?status=${statusFilter}`);
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      const data = await res.json();
      listings = data.listings || [];
      lastUpdated = data.last_updated;
      stats = {
        total: data.total || 0,
        matches: data.matches_count || 0,
        needs_review: data.needs_review_count || 0,
        rejected: data.rejected_count || 0,
      };
    } catch (err) {
      console.error('Failed to load listings:', err);
      loadError = err.message || 'Could not load listings.';
    } finally {
      isLoading = false;
    }
  }

  async function checkScraperStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();

      const wasFetching = isFetching;
      isFetching = Boolean(data.is_fetching);

      if (isFetching) {
        statusBanner = {
          type: 'running',
          text: data.message || 'Scraper pipeline in progress...',
        };
      } else if (wasFetching && !isFetching) {
        if (data.status === 'completed') {
          statusBanner = {
            type: 'completed',
            text: 'Scraping finished. Listings updated.',
          };
          loadListings();
        } else if (data.status === 'error') {
          statusBanner = {
            type: 'error',
            text: data.message || 'Scraper encountered an error.',
          };
        }
      }
    } catch (err) {
      console.error('Failed to check status:', err);
    }
  }

  async function triggerFetch() {
    if (isFetching) return;
    try {
      isFetching = true;
      statusBanner = {
        type: 'running',
        text: 'Starting scraper pipeline...',
      };
      const res = await fetch('/api/fetch', { method: 'POST' });
      if (!res.ok && res.status !== 409) {
        throw new Error(`Failed to trigger fetch (${res.status})`);
      }
      pollStatus();
    } catch (err) {
      isFetching = false;
      statusBanner = {
        type: 'error',
        text: `Could not trigger fetch: ${err.message}`,
      };
    }
  }

  function pollStatus() {
    if (pollTimer) clearInterval(pollTimer);
    checkScraperStatus();
    pollTimer = setInterval(async () => {
      await checkScraperStatus();
      if (!isFetching) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }, 2500);
  }

  function selectStatus(status) {
    statusFilter = status;
    loadListings();
  }

  function handleSort(key) {
    if (sortBy === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = key;
      // Price and Date default to ascending (cheapest / newest first); score and area default to descending
      sortDir = (key === 'price' || key === 'date') ? 'asc' : 'desc';
    }
  }

  function formatDaysAgo(days) {
    if (days === undefined || days === null) return null;
    if (days === 0) return 'Today';
    if (days === 1) return '1 day ago';
    return `${days} days ago`;
  }

  function getAgeClass(days) {
    if (days === undefined || days === null) return '';
    if (days >= 5) return 'age-red';
    if (days >= 3) return 'age-yellow';
    return '';
  }

  onMount(async () => {
    await loadListings();
    await checkScraperStatus();
    if (isFetching) {
      pollStatus();
    }
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  let filteredListings = $derived(
    listings
      .filter((item) => {
        if (!searchQuery.trim()) return true;
        const q = searchQuery.toLowerCase().trim();
        const l = item.listing || {};
        const searchTarget = [
          l.title,
          l.address,
          l.neighborhood,
          l.city,
          l.source,
          l.interior,
          l.property_type,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return searchTarget.includes(q);
      })
      .slice()
      .sort((a, b) => {
        let diff = 0;
        if (sortBy === 'score') {
          diff = (a.score ?? 0) - (b.score ?? 0);
        } else if (sortBy === 'price') {
          diff = (a.listing?.price ?? 0) - (b.listing?.price ?? 0);
        } else if (sortBy === 'area') {
          diff = (a.listing?.living_area_m2 ?? 0) - (b.listing?.living_area_m2 ?? 0);
        } else if (sortBy === 'date') {
          diff = (a.listing?.posted_days_ago ?? 9999) - (b.listing?.posted_days_ago ?? 9999);
        }
        return sortDir === 'asc' ? diff : -diff;
      })
  );

  function formatDate(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + d.toLocaleDateString();
    } catch {
      return isoStr;
    }
  }
</script>

<div class="container">
  <header class="app-header">
    <nav>
      <ul>
        <li>
          <div class="brand-title">
            <h1>Dutch Apartment Hunter</h1>
            {#if stats.matches > 0}
              <span class="brand-subtitle">{stats.matches} matches</span>
            {/if}
          </div>
        </li>
      </ul>
      <ul>
        <li>
          <button
            class="contrast action-btn"
            aria-busy={isFetching}
            disabled={isFetching}
            onclick={triggerFetch}
          >
            {#if !isFetching}
              <RefreshCw size={15} />
            {/if}
            <span>{isFetching ? 'Fetching…' : 'Fetch new listings'}</span>
          </button>
        </li>
      </ul>
    </nav>
  </header>

  <main>
    {#if statusBanner}
      <div class="status-banner {statusBanner.type}">
        <span class="banner-content">
          {#if statusBanner.type === 'running'}
            <RefreshCw size={15} class="spin" />
          {:else if statusBanner.type === 'completed'}
            <CheckCircle2 size={15} />
          {:else}
            <AlertCircle size={15} />
          {/if}
          <span>{statusBanner.text}</span>
        </span>
        <button
          type="button"
          class="banner-close"
          onclick={() => (statusBanner = null)}
        >
          ✕
        </button>
      </div>
    {/if}

    <div class="controls-section">
      <!-- Status Tabs -->
      <div class="segmented-control" role="group">
        <button
          type="button"
          class={statusFilter === 'MATCH' ? 'active' : 'outline'}
          onclick={() => selectStatus('MATCH')}
        >
          Matches ({stats.matches})
        </button>
        <button
          type="button"
          class={statusFilter === 'NEEDS_REVIEW' ? 'active' : 'outline'}
          onclick={() => selectStatus('NEEDS_REVIEW')}
        >
          Needs review ({stats.needs_review})
        </button>
        <button
          type="button"
          class={statusFilter === 'REJECTED' ? 'active' : 'outline'}
          onclick={() => selectStatus('REJECTED')}
        >
          Rejected ({stats.rejected})
        </button>
        <button
          type="button"
          class={statusFilter === 'ALL' ? 'active' : 'outline'}
          onclick={() => selectStatus('ALL')}
        >
          All ({stats.total})
        </button>
      </div>

      <!-- Sort Buttons & Search Bar -->
      <div class="toolbar-row">
        <div class="sort-toolbar">
          <span class="sort-caption">Sort:</span>
          <div class="sort-buttons" role="group">
            <button
              type="button"
              class={sortBy === 'score' ? 'active' : 'outline'}
              onclick={() => handleSort('score')}
              title="Click to toggle score order"
            >
              <Award size={14} class="sort-icon" />
              <span>Score</span>
              {#if sortBy === 'score'}
                {#if sortDir === 'desc'}
                  <ArrowDown size={13} class="sort-dir-icon" />
                {:else}
                  <ArrowUp size={13} class="sort-dir-icon" />
                {/if}
              {/if}
            </button>

            <button
              type="button"
              class={sortBy === 'price' ? 'active' : 'outline'}
              onclick={() => handleSort('price')}
              title="Click to toggle price order"
            >
              <Euro size={14} class="sort-icon" />
              <span>Price</span>
              {#if sortBy === 'price'}
                {#if sortDir === 'asc'}
                  <ArrowUp size={13} class="sort-dir-icon" />
                {:else}
                  <ArrowDown size={13} class="sort-dir-icon" />
                {/if}
              {/if}
            </button>

            <button
              type="button"
              class={sortBy === 'area' ? 'active' : 'outline'}
              onclick={() => handleSort('area')}
              title="Click to toggle area order"
            >
              <Maximize2 size={14} class="sort-icon" />
              <span>Area</span>
              {#if sortBy === 'area'}
                {#if sortDir === 'desc'}
                  <ArrowDown size={13} class="sort-dir-icon" />
                {:else}
                  <ArrowUp size={13} class="sort-dir-icon" />
                {/if}
              {/if}
            </button>

            <button
              type="button"
              class={sortBy === 'date' ? 'active' : 'outline'}
              onclick={() => handleSort('date')}
              title="Click to toggle newest/oldest"
            >
              <Clock size={14} class="sort-icon" />
              <span>Date</span>
              {#if sortBy === 'date'}
                {#if sortDir === 'asc'}
                  <ArrowUp size={13} class="sort-dir-icon" />
                {:else}
                  <ArrowDown size={13} class="sort-dir-icon" />
                {/if}
              {/if}
            </button>
          </div>
        </div>

        <div class="search-box">
          <input
            type="search"
            placeholder="Filter by street, city, source..."
            bind:value={searchQuery}
          />
        </div>
      </div>
    </div>

    {#if isLoading}
      <div class="state-message">
        <p aria-busy="true">Loading listings…</p>
      </div>
    {:else if loadError}
      <div class="state-message">
        <article style="text-align: center;">
          <AlertCircle size={28} style="color: var(--pico-del-color); margin-bottom: 0.5rem;" />
          <p><strong>Failed to load listings:</strong> {loadError}</p>
          <button class="outline" onclick={loadListings}>Retry</button>
        </article>
      </div>
    {:else if filteredListings.length === 0}
      <article class="state-message">
        <p style="margin: 0; text-align: center; color: var(--pico-muted-color);">
          {#if searchQuery.trim()}
            No listings matching "{searchQuery}".
          {:else if statusFilter === 'MATCH'}
            No matches found. Click <strong>Fetch new listings</strong> to run the scrapers.
          {:else}
            No listings found in this category.
          {/if}
        </p>
      </article>
    {:else}
      {#each filteredListings as item, idx (item.listing?.url || `${item.listing?.id || 'item'}-${idx}`)}
        <article class="listing-card">
          <div class="listing-top">
            <h2 class="listing-title">
              <a
                href={item.listing?.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {item.listing?.title || item.listing?.address || 'Untitled Property'}
              </a>
            </h2>
            <div class="listing-price">
              {#if item.listing?.price}
                €{item.listing.price.toLocaleString()}<small class="price-period"> / mo</small>
              {:else}
                Price on request
              {/if}
            </div>
          </div>

          <div class="listing-meta">
            {#if item.listing?.source}
              <span class="badge badge-source">{item.listing.source}</span>
            {/if}
            {#if item.listing?.city}
              <span class="meta-item">
                <MapPin size={14} />
                {item.listing.neighborhood ? `${item.listing.neighborhood}, ` : ''}{item.listing.city}
              </span>
            {/if}
            {#if item.listing?.living_area_m2}
              <span class="meta-item">
                <Maximize2 size={14} />
                {Math.round(item.listing.living_area_m2)} m²
              </span>
            {/if}
            {#if item.listing?.rooms}
              <span class="meta-item">
                <BedDouble size={14} />
                {item.listing.rooms} {item.listing.rooms === 1 ? 'room' : 'rooms'}
              </span>
            {/if}
            {#if item.listing?.interior}
              <span class="meta-item">{item.listing.interior}</span>
            {/if}
            {#if formatDaysAgo(item.listing?.posted_days_ago)}
              <span class="meta-item meta-posted {getAgeClass(item.listing?.posted_days_ago)}">
                <Clock size={14} />
                <span>{formatDaysAgo(item.listing.posted_days_ago)}</span>
              </span>
            {/if}
            {#if item.score !== undefined && item.score !== null}
              <span class="badge badge-score">Score: {item.score}</span>
            {/if}
            {#if item.status === 'REJECTED'}
              <span class="badge badge-rejected">{item.status}</span>
            {:else if item.status !== 'MATCH'}
              <span class="badge badge-review">{item.status}</span>
            {/if}
          </div>

          {#if item.reasons && item.reasons.length > 0}
            <div class="listing-reasons">
              <ul>
                {#each item.reasons as reason, rIdx (rIdx)}
                  <li><strong>Reason:</strong> {reason}</li>
                {/each}
              </ul>
            </div>
          {/if}

          {#if item.flags && item.flags.length > 0}
            <div class="listing-flags">
              <ul>
                {#each item.flags as flag, fIdx (fIdx)}
                  <li>{flag}</li>
                {/each}
              </ul>
            </div>
          {/if}

          <div class="listing-footer">
            <span class="footer-address">
              {#if item.listing?.postal_code}
                {item.listing.postal_code} •
              {/if}
              {#if item.listing?.address && item.listing.address !== item.listing.title}
                {item.listing.address}
              {:else}
                {item.listing?.city}
              {/if}
            </span>
            <a
              href={item.listing?.url}
              target="_blank"
              rel="noopener noreferrer"
              class="secondary outline portal-link"
              role="button"
            >
              <span>View on {item.listing?.source || 'portal'}</span>
              <ExternalLink size={13} />
            </a>
          </div>
        </article>
      {/each}
    {/if}
  </main>

  <footer class="app-footer">
    {#if lastUpdated}
      Last updated: {formatDate(lastUpdated)}
    {/if}
  </footer>
</div>
