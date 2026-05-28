
bonus_pool = 1000

#KOL 1

referredTVL_1 = 3000000 # amount referred
held_pct_1 = 0.40 # percentage that hold till the end
multiplier_1 = 1
w_1 = referredTVL_1 * multiplier_1 

#KOL 2

referredTVL_2 = 200000 # amount referred
held_pct_2 = 0.7 # percentage that hold till the end
multiplier_2 = 2
w_2 = referredTVL_2 * multiplier_2 

#KOL 3

referredTVL_3 = 1000000 # amount referred
held_pct_3 = 0.60 # percentage that hold till the end
multiplier_3 = 1.5
w_3 = referredTVL_3 * multiplier_3 

#KOL 4

referredTVL_4 = 100000 # amount referred
held_pct_4 = 0.8 # percentage that hold till the end
multiplier_4 = 2

# This is the weight in the distribution for each KOL
w_4 = referredTVL_4 * multiplier_4 

# This is the total weight for all KOLs
total_w = w_1 + w_2 + w_3 + w_4
total_tvl = referredTVL_1+referredTVL_2+referredTVL_3+referredTVL_4

# This is the percentage of the pool that belongs to each KOL
pool_dis_1 = w_1/total_w * bonus_pool
pool_dis_2 = w_2/total_w * bonus_pool
pool_dis_3 = w_3/total_w * bonus_pool
pool_dis_4 = w_4/total_w * bonus_pool

pool_flat_1 = referredTVL_1/total_tvl * bonus_pool
pool_flat_2 = referredTVL_2/total_tvl * bonus_pool
pool_flat_3 = referredTVL_3/total_tvl * bonus_pool
pool_flat_4 = referredTVL_4/total_tvl * bonus_pool

print("this would be the rewards for KOLs if we dont take into account bonus for long term commitment")
print(pool_flat_1,pool_flat_2,pool_flat_3,pool_flat_4)

print("this would be the rewards for KOLs taking into account multiplier")
print(pool_dis_1,pool_dis_2,pool_dis_3,pool_dis_4)

