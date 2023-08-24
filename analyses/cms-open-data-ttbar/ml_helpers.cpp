#include "fastforest.h"
#include <cmath>
#include <assert.h>
#include <map>
#include "ROOT/RVec.hxx"

std::map<std::string, fastforest::FastForest> get_fastforests (const std::string& path_to_models, size_t nfeatures) {

    std::vector<std::string> feature_names(nfeatures);
    for (int i = 0; i < nfeatures; ++i) {
        feature_names[i] = "f"+std::to_string(i);
    }

    auto fodd = fastforest::load_txt(path_to_models+"odd.txt", feature_names);
    auto feven = fastforest::load_txt(path_to_models+"even.txt", feature_names);
    return {{"even",feven}, {"odd", fodd}};
}

    
ROOT::RVecF inference(const std::vector<ROOT::RVecF> &features, const fastforest::FastForest &forest, bool check_features=false) {

    size_t npermutations = features.at(0).size();
    size_t nfeatures = features.size();
    ROOT::RVecF res(npermutations);
    float input[nfeatures];

    if (check_features) {
        for (int i = 0; i < nfeatures; ++i) {
            assert(features.at(i).size() == npermutations);
        }
    }
    
    for (int i = 0; i < npermutations; ++i) {
        for (int j = 0; j < nfeatures; ++j) {
            input[j] = features.at(j).at(i);
        }
        float score = forest(input, 0.0F);
        res[i] = 1./(1.+std::exp(-score));
    }

    return res;
}

// auto models = get_fastforests("models/", 20);
// auto feven = models["even"];
// auto fodd = models["odd"];