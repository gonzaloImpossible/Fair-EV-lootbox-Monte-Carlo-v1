# Rarible API Docs

Base URL: `https://bff.rarible.com`

## **/api/auth**

### **POST /api/auth/nonce**

Description: Generate a nonce used for wallet signature verification.

### **POST /api/auth/verify**

Description: Verify signed SIWE message and authenticate wallet session.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| message | Yes | string | SIWE message payload to verify. |
| signature | Yes | string | Signature for the SIWE message. |

## **/api/market/collections**

### **POST /api/market/collections/search**

Description: Search collections by text and optional blockchain/sort filters.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| text | Yes | string | Search keyword/text query. |
| size | No | number | Number of results (positive int, default 10). |
| blockchains | No | Blockchain[] | Filter collections by blockchain. |
| sort | No | CollectionSortEnum | Sort behavior for result ordering. |

### **POST /api/market/collections/leaderboard**

Description: Return collection leaderboard for selected period/sort.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| statisticPeriod | Yes | CollectionStatisticPeriod | Time window for leaderboard stats. |
| sort.field | Yes | CollectionSearchSort | Sort field. |
| sort.direction | Yes | CollectionSearchSortDirection | Sort direction. |
| size | No | number | Result size (positive int, default 50). |
| blockchains | No | Blockchain[] | Blockchain filter. |
| owner | No | UnionAddress | Owner-filtered leaderboard mode. |

### **GET /api/market/collections/spotlight**

Description: Return spotlight collections configured by backend.

### **GET /api/market/collections/whitelist**

Description: Return collection whitelist for a blockchain.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchain | Yes | Blockchain | Target blockchain for whitelist. |

### **GET /api/market/collections/featured**

Description: Return featured collections for a blockchain.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchain | Yes | Blockchain | "ALL" | Blockchain filter or all blockchains. |

### **GET /api/market/collections/:id/activity**

Description: Fetch collection activity feed with cursor pagination.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

### **GET /api/market/collections/:id/holders**

Description: Fetch collection holders list.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

### **GET /api/market/collections/:id/offer-groups**

Description: Fetch grouped offers for a collection.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

### **POST /api/market/collections/:id/offers**

Description: Fetch offers for a collection with pagination/sizing.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |
| size | No | number | Requested page size. |

### **GET /api/market/collections/:id/floor-price-change**

Description: Get floor price change for a selected period.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| period | Yes | CollectionFloorPriceChangePeriod | Time period for floor change calculation. |

## **/api/market/nfts**

### **POST /api/market/nfts/search**

Description: Search NFTs using shared legacy search schema.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| SEARCH_PARAMS_SCHEMA fields | Mixed | object | Filter/sort/pagination fields from shared schema. |

### **GET /api/market/nfts/promoted**

Description: Get promoted NFTs for a blockchain.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchain | Yes | Blockchain | "ALL" | Blockchain selector. |

### **POST /api/market/nfts/activities**

Description: Fetch activity entries for specific NFT IDs.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| itemIds | Yes | NftId[] | NFT IDs to query (min 1, max 50). |
| cursor | No | string | Pagination cursor. |
| from | No | string | Optional start timestamp/marker. |
| types | No | ("SELL" | "MINT")[] | Activity type filter (default SELL+MINT). |

### **GET /api/market/nfts/:id/activity**

Description: Fetch activity feed for a specific NFT.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

## **/api/market/profile**

### **POST /api/market/profile/:address/activity**

Description: Fetch profile activity for wallet address.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchains | Yes | Blockchain[] | Blockchain filter list (currently single chain expected). |
| cursor | No | string | Pagination cursor. |

### **POST /api/market/profile/:address/bids**

Description: Fetch active bids made by wallet address.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |
| size | No | number | Page size. |
| blockchains | No | Blockchain[] | Blockchain filter list. |

## **/api/market/drops**

### **POST /api/market/drops/search**

Description: Search/filter drops by status and blockchain.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| size | No | number | Result size (default 50). |
| status | No | DropStatus | DropStatus[] | Status filter. |
| blockchains | No | Blockchain[] | Blockchain filter. |

### **POST /api/market/drops/spotlight**

Description: Return spotlight drops for a blockchain.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchain | Yes | Blockchain | "ALL" | Blockchain selector. |

### **POST /api/market/drops/batch/minted**

Description: Get minted totals for multiple drop collection IDs.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| ids | Yes | CollectionId[] | Collection IDs (max 100). |
| owner | No | UnionAddress | Include owner-specific mint counts. |

### **GET /api/market/drops/:id/activity**

Description: Get mint activity for a drop collection.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

## **/api/market/rewards**

### **GET /api/market/rewards/leaderboard**

Description: Fetch rewards leaderboard page.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |
| blockchain | No | string | Optional chain filter. |

### **GET /api/market/rewards/:address**

Description: Fetch earned reward data for wallet.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| blockchain | No | string | Optional chain filter. |

## **/api/market/merchants**

### **GET /api/market/merchants/slug/:slug**

Description: Get merchant by slug with optional pages/collections.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| includePages | No | boolean | Include merchant pages (default false). |
| includeCollections | No | boolean | Include collections (default false). |

## **/api/monitoring/streams**

### **GET /api/monitoring/streams/by-status**

Description: Internal monitoring stream query by statuses.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| statuses | Yes | string | Comma-separated stream statuses. |

## **/api/streaming/users**

### **GET /api/streaming/users/**

Description: Resolve/fetch streaming user profile by wallet/ENS.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| wallet | Yes | string | Wallet address or ENS name. |

### **POST /api/streaming/users/**

Description: Create/update authenticated user profile.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| username | No | string | Public username. |
| displayName | No | string | Display name. |
| bio | No | string | Profile bio. |
| email | No | string | Email (can be empty string). |
| avatarUrl | No | string | Avatar URL (can be empty string). |

## **/api/streaming/follows**

### **GET /api/streaming/follows/**

Description: Check follow status or fetch follower/following lists/counts.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| follower | No | string | Follower wallet address. |
| following | No | string | Following wallet address. |
| address | No | string | Subject wallet for list/count mode. |
| type | No | "followers" | "following" | Mode selector when address provided. |
| list | No | "true" | "false" | Return list vs count. |

### **DELETE /api/streaming/follows/**

Description: Unfollow a target address.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| following | Yes | string | Target wallet to unfollow. |

## **/api/streaming/reviews**

### **GET /api/streaming/reviews/**

Description: Fetch reviews for a reviewee address.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| reviewee | Yes | string | Address being reviewed. |

### **POST /api/streaming/reviews/**

Description: Submit a review as authenticated user.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| revieweeAddress | Yes | string | Address being reviewed. |
| rating | Yes | number | Integer rating 1-5. |
| comment | No | string | Optional review text. |

## **/api/streaming/streams**

### **GET /api/streaming/streams/**

Description: List streams with filters.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| creator | No | string | Creator wallet filter. |
| live | No | "true" | "false" | Live-only filter flag. |
| ended | No | "true" | "false" | Ended-only filter flag. |
| limit | No | string | Limit; transformed to number. |

### **POST /api/streaming/streams/**

Description: Create a new stream.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| title | Yes | string | Stream title. |
| description | No | string | Stream description. |
| categoryId | No | uuid | null | Category ID. |
| scheduledAt | No | datetime | null | Scheduled start datetime. |
| hasMinting | No | boolean | Minting enabled flag. |
| previewImageUrl | No | url | null | Stream cover image URL. |
| products | No | any | null | Associated products payload. |
| pinnedProductUrl | No | string | null | Pinned product URL. |
| fundraisingGoalId | No | uuid | null | Linked fundraising goal. |
| giveawayProductUrl | No | url | null | Giveaway product URL. |

### **GET /api/streaming/streams/activity/:streamId**

Description: Fetch stream product activity feed.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| cursor | No | string | Pagination cursor. |

### **GET /api/streaming/streams/liked/**

Description: Fetch streams liked by a user.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| userAddress | Yes | string | User wallet address. |

### **GET /api/streaming/streams/live-status/**

Description: Batch fetch live statuses for stream IDs.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| ids | Yes | string | Comma-separated stream IDs (max 50). |

### **GET /api/streaming/streams/:id/likes/**

Description: Get like count and optional user-like status.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| userAddress | No | string | Include isLiked status for this user. |

### **GET /api/streaming/streams/:id/playback/**

Description: Resolve stream playback URL and metadata.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| playbackId | Yes | string | Playback/video fallback ID. |

### **GET /api/streaming/streams/:id/views/**

Description: Fetch total view count for stream playback asset.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| playbackId | No | string | Optional fallback playback ID. |

## **/api/streaming/spotlight**

### **GET /api/streaming/spotlight/**

Description: Fetch current spotlight stream(s).

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| all | No | "true" | "false" | Return all spotlight records when true. |

## **/api/streaming/ens**

### **GET /api/streaming/ens/resolve**

Description: Resolve wallet address to ENS name.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| address | Yes | string | Wallet address to resolve. |

## **/api/streaming/tips**

### **POST /api/streaming/tips/**

Description: Submit a tip transaction for a stream.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| streamId | Yes | uuid | Target stream ID. |
| amount | Yes | decimal string | Tip amount in token units. |
| currencyAddress | Yes | string | Token contract address. |
| currencySymbol | Yes | string | Token symbol. |
| blockchain | Yes | string | Chain identifier. |
| txHash | Yes | string | Transaction hash. |
| message | No | string | Optional tip message (max 200). |

### **GET /api/streaming/tips/:streamId**

Description: List tips for a stream.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| limit | No | string | Result limit; transformed to number. |
| offset | No | string | Offset; transformed to number. |

## **/api/streaming/fundraising**

### **GET /api/streaming/fundraising/**

Description: List fundraising goals with optional filters.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| creator | No | string | Creator wallet address filter. |
| active | No | string | Boolean-like string transformed to bool. |
| limit | No | string | Page limit; transformed to number. |
| offset | No | string | Page offset; transformed to number. |

## **/api/streaming/coinflow**

### **GET /api/streaming/coinflow/test-link**

Description: Generate test checkout link for debugging Coinflow flow.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| orderId | No | string | Override test order ID. |
| wallet | No | string | Override test wallet address. |

## **/api/streaming/giveaways**

### **GET /api/streaming/giveaways/:giveawayId/is-participant**

Description: Check whether a wallet participates in giveaway.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| walletAddress | Yes | string | Wallet to check. |

## **/api/streaming/chat**

### **GET /api/streaming/chat/:chatId**

Description: Fetch messages for a chat thread.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| limit | No | string | Message count limit (default 100). |
| skip | No | string | Message offset (default 0). |

### **POST /api/streaming/chat/:chatId**

Description: Post message to chat thread.

| **Body Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| content | Yes | string | Message content (1..1000 chars). |
| latencyTracking | No | object | Optional client timing metadata. |

## **/api/e2e**

### **GET /api/e2e/items/:itemId**

Description: Fetch E2E item state and optionally poll for expected order status.

| **Query Param** | **Required** | **Type** | **Description** |
| --- | --- | --- | --- |
| expectOrder | No | "true" | "false" | Enables polling mode. |
| timeout | No | string | Poll timeout in milliseconds. |